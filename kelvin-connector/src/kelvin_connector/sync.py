import json
import re
from typing import cast, final
from uuid import UUID

from kelvin_connector.consumer import HOST_GROUP_NAME_RE
from kelvin_connector.models import (
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    GroupProperties,
    GuardianRole,
    HostGroupCreateEvent,
    HostGroupDeleteEvent,
    HostGroupModifyEvent,
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
from provisioning_consumer_lib.dn import DN
from pydantic import BaseModel
from typing_extensions import override
from ucsschool_objects import (
    UNLOADED,
    And,
    DNIDMapper,
    Filter,
    Group,
    KelvinStorageSession,
    KelvinStorageSessionFactory,
    LoadSpec,
    NotFound,
    ObjectType,
    Operator,
    Or,
    Role,
    School,
    SchoolMembership,
    SearchQuery,
    UnloadedType,
    UnsetType,
    User,
    track_changes,
)

DEFAULT_NUBUS_SOURCE_UID = "nubus"

# Replace reference collections atomically instead of diffing them
# element-wise: element-wise diffs can produce operations inside the
# referenced objects (e.g. /school_memberships/<id>/groups/0/roles),
# which the user manager rejects.
_USER_REPLACE_FIELDS = frozenset(
    {
        "legal_wards",
        "legal_guardians",
        "school_memberships/*/groups",
        "school_memberships/*/roles",
    }
)

# Never stored in the cache: large binary payloads and secrets.
_UDM_PROPERTIES_DENYLIST = frozenset({"jpegPhoto", "password"})

# The first ou= RDN of a DN, like ucs-school-lib's SchoolSearchBase.getOU.
_RE_SCHOOL_OU = re.compile(r"(?:^|,)ou=([^,]+)", re.IGNORECASE)


def _school_ou_from_dn(dn: str) -> str | None:
    """The school OU a DN resides in, or None for DNs outside any OU.

    The user's primary school is its LDAP position, not the first entry of
    the multi-valued ``school`` UDM property — that list is unordered.
    """
    match = _RE_SCHOOL_OU.search(dn)
    return match.group(1) if match else None


def _server_hostname(value: str | None) -> str | None:
    """Reduce a server reference to its hostname (leaf cn).

    UDM exposes the share file servers as DNs; the cache stores hostnames to
    match what the v1 API resolves via computer_dn2name. A value that is
    already a bare hostname (no DN syntax) is returned unchanged.
    """
    if not value:
        return None
    return DN(value).rdn[1] if "=" in value else value


def _udm_properties(properties: BaseModel) -> dict[str, object]:
    """The full UDM properties of an event as a JSON-safe dict.

    Stored verbatim (minus the denylist) instead of only the configured
    mapped properties: the API filters at read time, so changing the
    mapped-properties configuration does not require a resync.
    """
    serialized = cast("dict[str, object]", json.loads(properties.json()))
    return {key: value for key, value in serialized.items() if key not in _UDM_PROPERTIES_DENYLIST}


class SynchronizationException(Exception):
    pass


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
                logger.debug("{} DN {!r} not yet in mapper, skipping", log_label, dn)
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

    async def _fetch_members_by_dns(
        self,
        dns: list[str],
        school: School,
        mapper: DNIDMapper,
        storage: KelvinStorageSession,
    ) -> set[User]:
        """Fetch member users that hold a membership for the given school.

        A (user, school) membership row is created only by the user's own
        events, and a group event can reference a member before that row
        exists — through event ordering, or because the user's event was
        lost. Linking such a member would fail the whole group sync with
        NotFound, so drop the member with a warning instead: the link is
        established by the member's own event, which carries the group DN.
        """
        known_ids = await self._dns_to_known_ids(mapper, ObjectType.USER, dns, "Member")
        if not known_ids:
            return set()
        members = set(
            await storage.users.search(
                SearchQuery(
                    And(
                        clauses=(
                            Filter(field="public_id", op=Operator.IN, value=known_ids),
                            Filter(
                                field="schools.public_id",
                                op=Operator.EQ,
                                value=str(school.public_id),
                            ),
                        )
                    )
                ),
                limit=len(known_ids),
            )
        )
        found_ids = {str(member.public_id) for member in members}
        for missing_id in sorted(set(known_ids) - found_ids):
            logger.warning(
                "Member {} has no membership for school {!r} (yet), skipping; "
                "the link is established when the member's own event arrives",
                missing_id,
                school.name,
            )
        return members

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
        primary_school: str | None,
    ) -> dict[UUID, SchoolMembership]:
        """Build one membership per school, marking exactly one as primary.

        ``primary_school`` is the OU from the user's DN. When it matches none
        of the schools (e.g. the DN's OU was dropped as unknown), the first
        school is primary, as the only remaining order signal.
        """
        primary_id: UUID | UnsetType | None = None
        if primary_school:
            for school in schools:
                if school.name.lower() == primary_school.lower():
                    primary_id = school.public_id
                    break
        if primary_id is None and schools:
            primary_id = schools[0].public_id

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
        for school in schools:
            assert not isinstance(school.public_id, UnsetType)

            school_role_names = {r.role for r in roles if r.school == school.name}

            school_groups: set[Group] = set()
            for group in groups:
                assert not isinstance(group.school, UnloadedType)
                if group.school.public_id == school.public_id:
                    school_groups.add(group)

            result[school.public_id] = SchoolMembership(
                school,
                groups=school_groups,
                is_primary=(school.public_id == primary_id),
                roles={roles_by_name[n] for n in school_role_names if n in roles_by_name},
            )
        return result

    # ── User event handlers ─────────────────────────────────────────────────

    @override
    async def handle_user_create(self, event: UserCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_user_create(event, storage, mapper)

    @override
    async def handle_user_modify(self, event: UserModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_user_modify(event, storage, mapper)

    @override
    async def handle_user_delete(self, event: UserDeleteEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_user_delete(event, storage)

    async def _handle_user_create(
        self, event: UserCreateEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        user_props = event.new.properties
        logger.debug("User {!r} has school property: {!r}", user_props.username, user_props.school)
        if user_props.school:
            schools = list(
                await storage.schools.search(
                    SearchQuery(
                        Or(
                            clauses=tuple(
                                Filter(field="name", op=Operator.EQ, value=s) for s in user_props.school
                            )
                        )
                    )
                )
            )
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
            schools, groups, user_props.ucsschoolRole, storage, _school_ou_from_dn(event.new.dn)
        )
        legal_wards = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalWard, "Legal ward", mapper, storage
        )
        legal_guardians = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalGuardian, "Legal guardian", mapper, storage
        )

        public_id = user_props.univentionObjectIdentifier
        try:
            # Load all fields: the object is the change-detection baseline, and
            # unloaded fields would diff as changed against the event values.
            current_user = await storage.users.get(public_id, load=LoadSpec.from_model(User))
        except NotFound:
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
                    source_uid=user_props.ucsschoolSourceUID or DEFAULT_NUBUS_SOURCE_UID,
                    school_memberships=school_memberships,
                    legal_wards=legal_wards,
                    legal_guardians=legal_guardians,
                    udm_properties=_udm_properties(user_props),
                )
            )
            await mapper.set_mapping(ObjectType.USER, event.new.dn, public_id)
            logger.info("User {!r} created (public_id={})", user_props.username, public_id)
        else:
            logger.info(
                "User {!r} already exists on create event, updating (public_id={})",
                user_props.username,
                public_id,
            )
            with track_changes(current_user, replace_fields=_USER_REPLACE_FIELDS) as tracker:
                self._apply_user_changes(
                    current_user,
                    user_props,
                    school_memberships,
                    legal_wards,
                    legal_guardians,
                )
            patch = tracker.patch
            if patch:
                await storage.users.modify(public_id, patch)
                logger.info(
                    "User {!r} modified from create event (public_id={})", user_props.username, public_id
                )
            else:
                logger.debug(
                    "No changes for user {!r} from create event (public_id={})",
                    user_props.username,
                    public_id,
                )

    async def _handle_user_delete(self, event: UserDeleteEvent, storage: KelvinStorageSession) -> None:
        public_id = event.old.properties.univentionObjectIdentifier
        try:
            await storage.users.delete(public_id)
        except NotFound:
            logger.info(
                "User {!r} not found on delete event, ignoring (public_id={})",
                event.old.properties.username,
                public_id,
            )
            return
        logger.info("User {!r} deleted (public_id={})", event.old.properties.username, public_id)

    async def _handle_user_modify(
        self, event: UserModifyEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        user_props = event.new.properties
        public_id = user_props.univentionObjectIdentifier
        logger.debug("Updating user {!r} (public_id={})", user_props.username, public_id)
        try:
            current_user = await storage.users.get(public_id, load=LoadSpec.from_model(User))
        except NotFound:
            # The user's create event was lost or dropped — the modify event
            # carries the full desired state, so repair the gap by creating.
            logger.warning(
                "User {!r} not found on modify event, creating (public_id={})",
                user_props.username,
                public_id,
            )
            await self._handle_user_create(
                UserCreateEvent(
                    timestamp=event.timestamp,
                    sequence_number=event.sequence_number,
                    new=event.new,
                ),
                storage,
                mapper,
            )
            return
        # A move/rename changes the dn but keeps the public_id — refresh the
        # mapping unconditionally so later events resolve the new dn.
        await mapper.set_mapping(ObjectType.USER, event.new.dn, public_id)

        raw_schools = user_props.school
        if raw_schools:
            schools = list(
                await storage.schools.search(
                    SearchQuery(
                        Or(
                            clauses=tuple(
                                Filter(field="name", op=Operator.EQ, value=s) for s in raw_schools
                            )
                        )
                    )
                )
            )
        else:
            schools = []
        groups = await self._fetch_groups_by_dns(user_props.groups, "Group", mapper, storage)
        school_memberships = await self._build_school_memberships(
            schools, groups, user_props.ucsschoolRole, storage, _school_ou_from_dn(event.new.dn)
        )
        legal_wards = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalWard, "Legal ward", mapper, storage
        )
        legal_guardians = await self._fetch_users_by_dns(
            user_props.ucsschoolLegalGuardian, "Legal guardian", mapper, storage
        )

        with track_changes(current_user, replace_fields=_USER_REPLACE_FIELDS) as tracker:
            self._apply_user_changes(
                current_user,
                user_props,
                school_memberships,
                legal_wards,
                legal_guardians,
            )
        patch = tracker.patch
        if patch:
            await storage.users.modify(public_id, patch)
            logger.info("User {!r} modified (public_id={})", user_props.username, public_id)
        else:
            logger.debug(
                "No changes for user {!r} (public_id={}), skipping modify",
                user_props.username,
                public_id,
            )

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
        user.source_uid = user_props.ucsschoolSourceUID or DEFAULT_NUBUS_SOURCE_UID
        user.school_memberships = school_memberships
        user.legal_wards = legal_wards
        user.legal_guardians = legal_guardians
        user.udm_properties = _udm_properties(user_props)

    # ── Group event handlers ────────────────────────────────────────────────

    @override
    async def handle_group_create(self, event: GroupCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_group_create(event, storage, mapper)

    @override
    async def handle_group_modify(self, event: GroupModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_group_modify(event, storage, mapper)

    @override
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
        members = await self._fetch_members_by_dns(group_props.users, school, mapper, storage)
        group_roles = await self._fetch_roles_by_entries(group_props.ucsschoolRole, storage)
        member_roles = await self._fetch_roles_by_guardian_entries(
            group_props.guardianMemberRoles, storage
        )

        public_id = group_props.univentionObjectIdentifier
        try:
            current_group = await storage.groups.get(public_id, load=LoadSpec.from_model(Group))
        except NotFound:
            logger.debug("Creating group {!r} (public_id={})", group_props.name, public_id)
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
                    # School classes and workgroups always have a share. v1
                    # has no read-time source for this and returns its model
                    # default (True); mirror that.
                    create_share=True,
                    roles=group_roles,
                    member_roles=member_roles,
                    description=group_props.description,
                    udm_properties=_udm_properties(group_props),
                )
            )
            await mapper.set_mapping(ObjectType.GROUP, event.new.dn, public_id)
            logger.info("Group {!r} created (public_id={})", group_props.name, public_id)
        else:
            logger.info(
                "Group {!r} already exists on create event, updating (public_id={})",
                group_props.name,
                public_id,
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
                    group_roles,
                    allowed_email_senders_users,
                    allowed_email_senders_groups,
                    members,
                    member_roles,
                )
            patch = tracker.patch
            if patch:
                await storage.groups.modify(public_id, patch)
                logger.info(
                    "Group {!r} modified from create event (public_id={})", group_props.name, public_id
                )
            else:
                logger.debug(
                    "No changes for group {!r} from create event (public_id={})",
                    group_props.name,
                    public_id,
                )

    async def _handle_group_delete(self, event: GroupDeleteEvent, storage: KelvinStorageSession) -> None:
        public_id = event.old.properties.univentionObjectIdentifier
        try:
            await storage.groups.delete(public_id)
        except NotFound:
            logger.info(
                "Group {!r} not found on delete event, ignoring (public_id={})",
                event.old.properties.name,
                public_id,
            )
            return
        logger.info("Group {!r} deleted (public_id={})", event.old.properties.name, public_id)

    async def _handle_group_modify(
        self, event: GroupModifyEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        group_props = event.new.properties
        public_id = group_props.univentionObjectIdentifier
        logger.debug("Updating group {!r} (public_id={})", group_props.name, public_id)
        try:
            current_group = await storage.groups.get(public_id, load=LoadSpec.from_model(Group))
        except NotFound:
            # The group's create event was lost or dropped — the modify event
            # carries the full desired state, so repair the gap by creating.
            logger.warning(
                "Group {!r} not found on modify event, creating (public_id={})",
                group_props.name,
                public_id,
            )
            await self._handle_group_create(
                GroupCreateEvent(
                    timestamp=event.timestamp,
                    sequence_number=event.sequence_number,
                    new=event.new,
                ),
                storage,
                mapper,
            )
            return
        # A move/rename changes the dn but keeps the public_id — refresh the
        # mapping unconditionally so later events resolve the new dn.
        await mapper.set_mapping(ObjectType.GROUP, event.new.dn, public_id)

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
        # When the event's school is not in the cache the group keeps its
        # stored school (see _apply_group_changes) — filter members against
        # the school the group will actually have.
        target_school = school if not isinstance(school, UnloadedType) else current_group.school
        members = await self._fetch_members_by_dns(group_props.users, target_school, mapper, storage)
        group_roles = await self._fetch_roles_by_entries(group_props.ucsschoolRole, storage)
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
                group_roles,
                allowed_email_senders_users,
                allowed_email_senders_groups,
                members,
                member_roles,
            )
        patch = tracker.patch
        if patch:
            await storage.groups.modify(public_id, patch)
            logger.info("Group {!r} modified (public_id={})", group_props.name, public_id)
        else:
            logger.debug(
                "No changes for group {!r} (public_id={}), skipping modify", group_props.name, public_id
            )

    def _apply_group_changes(
        self,
        group: Group,
        group_props: GroupProperties,
        school: School | UnloadedType,
        group_roles: set[Role],
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
        group.roles = group_roles
        group.allowed_email_senders_users = allowed_email_senders_users
        group.allowed_email_senders_groups = allowed_email_senders_groups
        group.members = members
        group.member_roles = member_roles
        group.create_share = True
        group.description = group_props.description
        group.udm_properties = _udm_properties(group_props)

    # ── School event handlers ───────────────────────────────────────────────

    @override
    async def handle_school_create(self, event: SchoolCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_school_create(event, storage, mapper)

    @override
    async def handle_school_modify(self, event: SchoolModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = self._mapper_factory(storage)
            await self._handle_school_modify(event, storage, mapper)

    @override
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
            # Servers are populated by the DC host group events, not the OU
            # event; start empty.
            educational_servers=set(),
            administrative_servers=set(),
            class_share_file_server=_server_hostname(school_props.ucsschoolClassShareFileServer),
            home_share_file_server=_server_hostname(school_props.ucsschoolHomeShareFileServer),
            udm_properties=_udm_properties(school_props),
        )
        try:
            current_school = await storage.schools.get(public_id)
        except NotFound:
            await storage.schools.create(school)
            await mapper.set_mapping(ObjectType.SCHOOL, event.new.dn, public_id)
            logger.info("School {!r} created (public_id={})", school_props.name, public_id)
        else:
            school_props = event.new.properties
            public_id = school_props.univentionObjectIdentifier
            logger.info(
                "School {!r} already exists on create event, updating (public_id={})",
                school_props.name,
                public_id,
            )
            with track_changes(current_school) as tracker:
                current_school.name = school_props.name
                current_school.display_name = school_props.displayName
                current_school.class_share_file_server = _server_hostname(
                    school_props.ucsschoolClassShareFileServer
                )
                current_school.home_share_file_server = _server_hostname(
                    school_props.ucsschoolHomeShareFileServer
                )
                current_school.udm_properties = _udm_properties(school_props)
            patch = tracker.patch
            if patch:
                await storage.schools.modify(public_id, patch)
                logger.info(
                    "School {!r} modified from create event (public_id={})", school_props.name, public_id
                )
            else:
                logger.debug(
                    "No changes for school {!r} from create event (public_id={})",
                    school_props.name,
                    public_id,
                )

    async def _handle_school_delete(
        self, event: SchoolDeleteEvent, storage: KelvinStorageSession
    ) -> None:
        public_id = event.old.properties.univentionObjectIdentifier
        try:
            await storage.schools.delete(public_id)
        except NotFound:
            logger.info(
                "School {!r} not found on delete event, ignoring (public_id={})",
                event.old.properties.name,
                public_id,
            )
            return
        logger.info("School {!r} deleted (public_id={})", event.old.properties.name, public_id)

    async def _handle_school_modify(
        self, event: SchoolModifyEvent, storage: KelvinStorageSession, mapper: DNIDMapper
    ) -> None:
        school_props = event.new.properties
        public_id = school_props.univentionObjectIdentifier
        logger.debug("Updating school {!r} (public_id={})", school_props.name, public_id)
        try:
            current_school = await storage.schools.get(public_id)
        except NotFound:
            # The school's create event was lost or dropped — the modify event
            # carries the full desired state, so repair the gap by creating.
            logger.warning(
                "School {!r} not found on modify event, creating (public_id={})",
                school_props.name,
                public_id,
            )
            await self._handle_school_create(
                SchoolCreateEvent(
                    timestamp=event.timestamp,
                    sequence_number=event.sequence_number,
                    new=event.new,
                ),
                storage,
                mapper,
            )
            return
        # A move/rename changes the dn but keeps the public_id — refresh the
        # mapping unconditionally so later events resolve the new dn.
        await mapper.set_mapping(ObjectType.SCHOOL, event.new.dn, public_id)
        with track_changes(current_school) as tracker:
            current_school.name = school_props.name
            current_school.display_name = school_props.displayName
            current_school.class_share_file_server = _server_hostname(
                school_props.ucsschoolClassShareFileServer
            )
            current_school.home_share_file_server = _server_hostname(
                school_props.ucsschoolHomeShareFileServer
            )
            current_school.udm_properties = _udm_properties(school_props)
        patch = tracker.patch
        if patch:
            await storage.schools.modify(public_id, patch)
            logger.info("School {!r} modified (public_id={})", school_props.name, public_id)
        else:
            logger.debug(
                "No changes for school {!r} (public_id={}), skipping modify",
                school_props.name,
                public_id,
            )

    async def handle_host_group_create(self, event: HostGroupCreateEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_host_group_change(event, storage)

    async def handle_host_group_modify(self, event: HostGroupModifyEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            await self._handle_host_group_change(event, storage)

    async def _handle_host_group_change(
        self, event: HostGroupModifyEvent | HostGroupCreateEvent, storage: KelvinStorageSession
    ) -> None:
        # The host group lists its members by DN; the cache stores server
        # hostnames (the leaf cn), matching what the v1 API resolves via
        # computer_dn2name. Otherwise schools would expose raw DNs.
        hosts = {DN(host).rdn[1] for host in event.new.properties.hosts}
        await self._set_school_servers(event.new.properties.name, hosts, storage)

    async def _set_school_servers(
        self,
        group_name: str,
        hosts: set[str],
        storage: KelvinStorageSession,
        *,
        missing_school_ok: bool = False,
    ) -> None:
        m = HOST_GROUP_NAME_RE.match(group_name)
        if m is None:
            raise SynchronizationException(f"Unexpected host group name {group_name!r}.")

        group_type = m.group(2)
        school_name = m.group(1)
        kind = "educational" if group_type == "Edukativnetz" else "administrative"

        schools = list(
            await storage.schools.search(
                SearchQuery(Filter(field="name", op=Operator.MATCHES_CI, value=school_name))
            )
        )
        if not schools:
            if missing_school_ok:
                logger.debug("School {!r} not in cache, nothing to clear for host group", school_name)
                return
            raise SynchronizationException(f"Unable to find school with name={school_name} in database.")
        school = schools[0]
        if isinstance(school.public_id, UnsetType):
            raise ValueError(f"Unexpected UnsetType in {school}")

        logger.debug("Setting {} servers for school {!r} to {}", kind, school_name, sorted(hosts))
        with track_changes(school) as tracker:
            match group_type:
                case "Edukativnetz":
                    school.educational_servers = hosts
                case "Verwaltungsnetz":
                    school.administrative_servers = hosts
                case _:  # pragma: no cover
                    raise SynchronizationException("Unreachable code reached.")

        patch = tracker.patch
        if patch:
            await storage.schools.modify(school.public_id, patch)
            logger.info(
                "Updated {} servers for school {!r} (public_id={})", kind, school_name, school.public_id
            )
        else:
            logger.debug(
                "No changes for {} servers of school {!r} (public_id={}), skipping modify",
                kind,
                school_name,
                school.public_id,
            )

    async def handle_host_group_delete(self, event: HostGroupDeleteEvent) -> None:
        # A deleted DC host group means the school no longer has those servers;
        # clear them so the cache does not keep stale entries (v1 reads the
        # group's members live and reports none once it is gone).
        async with self.storage_factory.transaction_scope() as storage:
            await self._set_school_servers(
                event.old.properties.name, set(), storage, missing_school_ok=True
            )
