from typing import cast, final
from uuid import UUID

from kelvin_connector.models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    GroupProperties,
    GuardianRole,
    SchoolCreateEvent,
    SchoolDeleteEvent,
    SchoolModifyEvent,
    UcsschoolRole,
    UserCreateEvent,
    UserDeleteEvent,
    UserModifyEvent,
    UserProperties,
)
from kelvin_connector.ports import DNIDMapperFactory, SynchronizationManagerProtocol
from loguru import logger
from ucsschool_objects.core.domain import LoadSpec, SearchQuery
from ucsschool_objects.core.domain.models import (
    UNLOADED,
    Group,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    UnsetType,
    User,
)
from ucsschool_objects.core.domain.patch import track_changes
from ucsschool_objects.core.domain.ports import KelvinStorageSession, KelvinStorageSessionFactory
from ucsschool_objects.core.domain.query import (
    Filter,
    Operator,
    Or,
)

from .nubus_compat import DNIDMapper, ObjectType


@final
class SynchronizationManager(SynchronizationManagerProtocol):
    def __init__(
        self,
        storage_factory: KelvinStorageSessionFactory,
        mapper_factory: DNIDMapperFactory,
    ) -> None:
        self.storage_factory = storage_factory
        self._mapper_factory = mapper_factory

    # ── Shared fetch helpers ────────────────────────────────────────────────

    async def _dns_to_known_ids(
        self,
        mapper: DNIDMapper,
        object_type: ObjectType,
        dns: list[str],
        log_label: str,
    ) -> list[str]:
        dn_to_id = await mapper.dns_to_public_ids(object_type, dns)
        for dn in dns:
            if dn not in dn_to_id:
                logger.info("{} DN {!r} not yet in mapper, skipping", log_label, dn)
        return [str(uid) for uid in dn_to_id.values()]

    async def _fetch_users_by_dns(
        self,
        dns: list[str],
        label: str,
        mapper: DNIDMapper,
        storage: KelvinStorageSession,
    ) -> set[User]:
        known_ids = await self._dns_to_known_ids(mapper, ObjectType.USER, dns, label)
        if not known_ids:
            return set()
        return set(
            await storage.users.search(
                SearchQuery(Filter(field="public_id", op=Operator.IN, value=known_ids))
            )
        )

    async def _fetch_groups_by_dns(
        self,
        dns: list[str],
        label: str,
        mapper: DNIDMapper,
        storage: KelvinStorageSession,
    ) -> set[Group]:
        known_ids = await self._dns_to_known_ids(mapper, ObjectType.GROUP, dns, label)
        if not known_ids:
            return set()
        return set(
            await storage.groups.search(
                SearchQuery(Filter(field="public_id", op=Operator.IN, value=known_ids))
            )
        )

    async def _fetch_roles_by_names(
        self, role_names: set[str], storage: KelvinStorageSession
    ) -> set[Role]:
        if not role_names:
            return set()
        return set(
            await storage.roles.search(
                SearchQuery(
                    Or(
                        clauses=tuple(
                            Filter(field="name", op=Operator.EQ, value=name) for name in role_names
                        )
                    )
                )
            )
        )

    async def _fetch_roles_by_entries(
        self, role_entries: list[UcsschoolRole], storage: KelvinStorageSession
    ) -> set[Role]:
        return await self._fetch_roles_by_names({r.role for r in role_entries}, storage)

    async def _fetch_roles_by_guardian_entries(
        self, guardian_roles: list[GuardianRole], storage: KelvinStorageSession
    ) -> set[Role]:
        return await self._fetch_roles_by_names({g.role_name for g in guardian_roles}, storage)

    async def _build_school_memberships(
        self,
        schools: list[School],
        groups: set[Group],
        roles: list[UcsschoolRole],
        storage: KelvinStorageSession,
    ) -> dict[UUID, SchoolMembership]:
        all_role_names = {r.role for r in roles}
        roles_by_name: dict[str, Role] = {}
        if all_role_names:
            roles_by_name = {
                cast(str, r.name): r
                for r in await storage.roles.search(
                    SearchQuery(
                        Or(
                            clauses=tuple(
                                Filter(field="name", op=Operator.EQ, value=n) for n in all_role_names
                            )
                        )
                    )
                )
            }
        result: dict[UUID, SchoolMembership] = {}
        for i, school in enumerate(schools):
            assert not isinstance(school.public_id, UnsetType)

            school_role_names = {r.role for r in roles if r.school == school.name}

            school_groups = set()
            for group in groups:
                assert not isinstance(group.school, UnloadedType)
                if group.school.public_id == school.public_id:
                    school_groups.add(group)

            result[school.public_id] = SchoolMembership(
                school,
                groups=school_groups,
                is_primary=(i == 0),
                roles={roles_by_name[n] for n in school_role_names if n in roles_by_name},
            )
        return result

    # ── User event handlers ─────────────────────────────────────────────────

    async def handle_user_create(self, event: UserCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_user_create(event, storage, mapper)

    async def handle_user_modify(self, event: UserModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_user_modify(event, storage, mapper)

    async def handle_user_delete(self, event: UserDeleteEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_user_delete(event, storage)

    async def _handle_user_create(
        self, event: UserCreateEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        user_props = event.new.properties
        logger.debug("User {!r} has school property: {!r}", user_props.username, user_props.school)
        if user_props.school:
            school_by_name = {
                s.name: s
                for s in await storage.schools.search(
                    SearchQuery(
                        Or(
                            clauses=tuple(
                                Filter(field="name", op=Operator.EQ, value=s) for s in user_props.school
                            )
                        )
                    )
                )
            }
            schools = [school_by_name[name] for name in user_props.school if name in school_by_name]
        else:
            schools = []
        if not schools:
            logger.warning(
                "School(s) {!r} not found for user {!r}, dropping event",
                user_props.school,
                user_props.username,
            )
            return
        logger.debug(
            "Found {} school(s) for user {!r}: {!r}",
            len(schools),
            user_props.username,
            [s.name for s in schools],
        )

        groups = await self._fetch_groups_by_dns(user_props.groups, "Group", mapper, storage)
        school_memberships = await self._build_school_memberships(
            schools, groups, user_props.ucsschoolRole, storage
        )
        legal_wards = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalWard, "Legal ward", mapper, storage
        )
        legal_guardians = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalGuardian, "Legal guardian", mapper, storage
        )

        public_id = user_props.univentionObjectIdentifier
        await storage.users.create(
            User(
                public_id=public_id,
                name=user_props.username,
                firstname=user_props.firstname,
                lastname=user_props.lastname,
                active=not user_props.disabled,
                email=user_props.mailPrimaryAddress,
                birthday=user_props.birthday,
                expiration_date=user_props.userexpiry,
                record_uid=user_props.ucsschoolRecordUID or user_props.username,
                source_uid=user_props.ucsschoolSourceUID or "UMC",
                school_memberships=school_memberships,
                legal_wards=legal_wards,
                legal_guardians=legal_guardians,
            )
        )
        await mapper.set_mapping(ObjectType.USER, event.new.dn, public_id)

    async def _handle_user_delete(self, event: UserDeleteEvent, storage: KelvinStorageSession) -> None:
        public_id = event.old.properties.univentionObjectIdentifier
        await storage.users.delete(public_id)

    async def _handle_user_modify(
        self, event: UserModifyEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        user_props = event.new.properties
        public_id = user_props.univentionObjectIdentifier
        current_user = await storage.users.get(
            public_id,
            load=LoadSpec.from_attributes("school_memberships", "legal_wards", "legal_guardians"),
        )

        raw_schools = user_props.school
        if raw_schools:
            school_by_name = {
                s.name: s
                for s in await storage.schools.search(
                    SearchQuery(
                        Or(
                            clauses=tuple(
                                Filter(field="name", op=Operator.EQ, value=s) for s in raw_schools
                            )
                        )
                    )
                )
            }
            # sort by order of raw_schools, as the primary school
            # in _build_school_memberships is derived from the first school
            schools = [school_by_name[name] for name in raw_schools if name in school_by_name]
        else:
            schools = []
        groups = await self._fetch_groups_by_dns(user_props.groups, "Group", mapper, storage)
        school_memberships = await self._build_school_memberships(
            schools, groups, user_props.ucsschoolRole, storage
        )
        legal_wards = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalWard, "Legal ward", mapper, storage
        )
        legal_guardians = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalGuardian, "Legal guardian", mapper, storage
        )

        with track_changes(
            current_user, replace_fields=frozenset({"legal_wards", "legal_guardians"})
        ) as tracker:
            self._apply_user_changes(
                current_user,
                user_props,
                school_memberships,
                legal_wards,
                legal_guardians,
            )
        if tracker.patch:
            await storage.users.modify(public_id, tracker.patch)

    def _apply_user_changes(
        self,
        user: User,
        user_props: UserProperties,
        school_memberships: dict[UUID, SchoolMembership],
        legal_wards: set[User],
        legal_guardians: set[User],
    ) -> None:
        user.name = user_props.username
        user.firstname = user_props.firstname
        user.lastname = user_props.lastname
        user.active = not user_props.disabled
        user.email = user_props.mailPrimaryAddress
        user.birthday = user_props.birthday
        user.expiration_date = user_props.userexpiry
        user.record_uid = user_props.ucsschoolRecordUID or user_props.username
        user.source_uid = user_props.ucsschoolSourceUID
        user.school_memberships = school_memberships
        user.legal_wards = legal_wards
        user.legal_guardians = legal_guardians

    # ── Group event handlers ────────────────────────────────────────────────

    async def handle_group_create(self, event: GroupCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_group_create(event, storage, mapper)

    async def handle_group_modify(self, event: GroupModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_group_modify(event, storage, mapper)

    async def handle_group_delete(self, event: GroupDeleteEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_group_delete(event, storage)

    async def _handle_group_create(
        self, event: GroupCreateEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        group_props = event.new.properties
        group_name = group_props.name
        school_name = (
            group_props.ucsschoolRole[0].school
            if group_props.ucsschoolRole
            else group_name.split("-")[0]
        )
        logger.debug("Looking up school {!r} for group {!r}", school_name, group_name)

        found_schools = list(
            await storage.schools.search(
                SearchQuery(Filter(field="name", op=Operator.EQ, value=school_name))
            )
        )
        if not found_schools:
            logger.warning(
                "School {!r} not found for group {!r}, dropping event",
                school_name,
                group_name,
            )
            return
        school = found_schools[0]

        allowed_email_senders_users = await self._fetch_users_by_dns(
            group_props.allowedEmailUsers, "Email sender user", mapper, storage
        )
        allowed_email_senders_groups = await self._fetch_groups_by_dns(
            group_props.allowedEmailGroups, "Email sender group", mapper, storage
        )
        members = await self._fetch_users_by_dns(group_props.users, "Member", mapper, storage)
        group_type_roles = await self._fetch_roles_by_entries(group_props.ucsschoolRole, storage)
        member_roles = await self._fetch_roles_by_guardian_entries(
            group_props.guardianMemberRoles, storage
        )

        public_id = group_props.univentionObjectIdentifier
        logger.debug("Creating group {}", group_props.name)
        await storage.groups.create(
            Group(
                public_id=public_id,
                name=group_props.name,
                display_name=group_props.name,
                record_uid=group_props.name,
                source_uid="kelvin-connector",
                email=group_props.mailAddress,
                school=school,
                allowed_email_senders_users=allowed_email_senders_users,
                allowed_email_senders_groups=allowed_email_senders_groups,
                members=members,
                create_share=False,
                roles=group_type_roles,
                member_roles=member_roles,
            )
        )
        logger.trace("Setting dn-id mapping {} -> {}", event.new.dn, public_id)
        await mapper.set_mapping(ObjectType.GROUP, event.new.dn, public_id)

    async def _handle_group_delete(self, event: GroupDeleteEvent, storage: KelvinStorageSession) -> None:
        public_id = event.old.properties.univentionObjectIdentifier
        await storage.groups.delete(public_id)

    async def _handle_group_modify(
        self, event: GroupModifyEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        group_props = event.new.properties
        public_id = group_props.univentionObjectIdentifier
        current_group = await storage.groups.get(
            public_id,
            load=LoadSpec.from_attributes(
                "school",
                "roles",
                "allowed_email_senders_users",
                "allowed_email_senders_groups",
                "members",
                "member_roles",
            ),
        )

        school_name = (
            group_props.ucsschoolRole[0].school
            if group_props.ucsschoolRole
            else group_props.name.split("-")[0]
        )
        found = list(
            await storage.schools.search(
                SearchQuery(Filter(field="name", op=Operator.EQ, value=school_name))
            )
        )
        school: School | UnloadedType = found[0] if found else UNLOADED

        allowed_email_senders_users = await self._fetch_users_by_dns(
            group_props.allowedEmailUsers, "Email sender user", mapper, storage
        )
        allowed_email_senders_groups = await self._fetch_groups_by_dns(
            group_props.allowedEmailGroups, "Email sender group", mapper, storage
        )
        members = await self._fetch_users_by_dns(group_props.users, "Member", mapper, storage)
        group_type_roles = await self._fetch_roles_by_entries(group_props.ucsschoolRole, storage)
        member_roles = await self._fetch_roles_by_guardian_entries(
            group_props.guardianMemberRoles, storage
        )

        with track_changes(
            current_group,
            replace_fields=frozenset(
                {
                    "school",
                    "roles",
                    "allowed_email_senders_users",
                    "allowed_email_senders_groups",
                    "members",
                    "member_roles",
                }
            ),
        ) as tracker:
            self._apply_group_changes(
                current_group,
                group_props,
                school,
                group_type_roles,
                allowed_email_senders_users,
                allowed_email_senders_groups,
                members,
                member_roles,
            )
        if tracker.patch:
            await storage.groups.modify(public_id, tracker.patch)

    def _apply_group_changes(
        self,
        group: Group,
        group_props: GroupProperties,
        school: School | UnloadedType,
        group_type_roles: set[Role],
        allowed_email_senders_users: set[User],
        allowed_email_senders_groups: set[Group],
        members: set[User],
        member_roles: set[Role],
    ) -> None:
        group.name = group_props.name
        group.display_name = group_props.name
        group.record_uid = group_props.name
        if group_props.mailAddress is not None:
            group.email = group_props.mailAddress
        if school is not UNLOADED:
            group.school = school
        group.roles = group_type_roles
        group.allowed_email_senders_users = allowed_email_senders_users
        group.allowed_email_senders_groups = allowed_email_senders_groups
        group.members = members
        group.member_roles = member_roles

    # ── School event handlers ───────────────────────────────────────────────

    async def handle_school_create(self, event: SchoolCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_school_create(event, storage, mapper)

    async def handle_school_modify(self, event: SchoolModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_school_modify(event, storage)

    async def handle_school_delete(self, event: SchoolDeleteEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_school_delete(event, storage)

    async def _handle_school_create(
        self, event: SchoolCreateEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        school_props = event.new.properties
        public_id = school_props.univentionObjectIdentifier
        school = School(
            public_id=public_id,
            name=school_props.name,
            display_name=school_props.displayName,
            record_uid=school_props.name,
            source_uid="kelvin-connector",
            educational_servers={"TODO"},
            administrative_servers={"TODO"},
        )
        await storage.schools.create(school)
        await mapper.set_mapping(ObjectType.SCHOOL, event.new.dn, public_id)
        logger.info("School {!r} created (public_id={})", school_props.name, public_id)

    async def _handle_school_delete(
        self, event: SchoolDeleteEvent, storage: KelvinStorageSession
    ) -> None:
        public_id = event.old.properties.univentionObjectIdentifier
        await storage.schools.delete(public_id)

    async def _handle_school_modify(
        self, event: SchoolModifyEvent, storage: KelvinStorageSession
    ) -> None:
        school_props = event.new.properties
        public_id = school_props.univentionObjectIdentifier
        current_school = await storage.schools.get(public_id)
        with track_changes(current_school) as tracker:
            current_school.name = school_props.name
            current_school.display_name = school_props.displayName
        if tracker.patch:
            await storage.schools.modify(public_id, tracker.patch)
