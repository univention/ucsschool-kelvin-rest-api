import uuid
from typing import Any, Callable, cast, final
from uuid import UUID

from kelvin_connector.models import (
    EventType,
    GroupEvent,
    SchoolEvent,
    UserEvent,
)
from kelvin_connector.ports import SynchronizationManagerProtocol
from loguru import logger
from ucsschool_objects.core.adapters.sqlalchemy.session import KelvinSqlAlchemySession
from ucsschool_objects.core.domain import LoadSpec, SearchQuery
from ucsschool_objects.core.domain.models import (
    UNLOADED,
    Group,
    School,
    SchoolMembership,
    UnsetType,
    User,
)
from ucsschool_objects.core.domain.patch import track_changes
from ucsschool_objects.core.domain.ports import KelvinStorageSessionFactory
from ucsschool_objects.core.domain.query import (
    Filter,
    Operator,
    Or,
)

from .nubus_compat import ObjectType, SQLAlchemyDNIDMapper

UDM_USER_PROPERTY_MAPPING = {
    "ucsschoolRecordUID": "record_uid",
    "ucsschoolSourceUID": "source_uid",
    "username": "name",
    "firstname": "firstname",
    "lastname": "lastname",
    "disabled": "active",
    "school": "school_memberships",
    "ucsschoolLegalWard": "legal_wards",
    "ucsschoolLegalGuardian": "legal_guardians",
    "e-mail": "email",
    "birthday": "birthday",
    "userexpiry": "expiration_date",
}

UDM_GROUP_PROPERTY_MAPPING = {
    "ucsschoolRecordUID": "record_uid",
    "ucsschoolSourceUID": "source_uid",
    "name": "name",
    "allowedEmailUsers": "allowed_email_senders_users",
    "allowedEmailGroups": "allowed_email_senders_groups",
    "school": "school",
    "mailAddress": "email",
}

UDM_SCHOOL_PROPERTY_MAPPING = {
    "name": "name",
    "displayName": "display_name",
    "ucsschoolHomeShareFileServer": "home_share_file_server",
    "ucsschoolClassShareFileServer": "class_share_file_server",
    # TODO: educational_servers, administrative_servers (no direct UDM property)
}


class UDMPropertyMapper:
    def __init__(self):
        self._mappings: dict[str, str] = {}
        self._hooks: dict[str, Callable[..., Any]] = {}

    def register_map(self, mapping: dict[str, str]) -> None:
        for source_key, target_key in mapping.items():
            if source_key in self._mappings:
                raise ValueError(f"Source key '{source_key}' is already registered.")
            if target_key in self._mappings.values():
                raise ValueError(f"Target key '{target_key}' is already registered.")
            self._mappings[source_key] = target_key

    def register_hook(self, source_key: str, func: Callable[..., Any]):
        if source_key not in self._mappings:
            raise ValueError(f"Source key '{source_key}' is not registered.")
        self._hooks[source_key] = func

    def map(self, source: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for source_key, target_key in self._mappings.items():
            if source_key not in source:
                continue
            value = source[source_key]
            if source_key in self._hooks:
                value = self._hooks[source_key](value)
            result[target_key] = value
        return result


@final
class SynchronizationManager(SynchronizationManagerProtocol):
    def __init__(
        self,
        storage_factory: KelvinStorageSessionFactory,
    ) -> None:
        self.storage_factory = storage_factory
        self._build_property_mapper()

    def _build_property_mapper(self) -> None:
        self.udm_property_mapper = UDMPropertyMapper()
        self.udm_property_mapper.register_map(UDM_USER_PROPERTY_MAPPING)
        self.udm_property_mapper.register_hook("disabled", lambda x: not x)

        self.udm_group_property_mapper = UDMPropertyMapper()
        self.udm_group_property_mapper.register_map(UDM_GROUP_PROPERTY_MAPPING)

        self.udm_school_property_mapper = UDMPropertyMapper()
        self.udm_school_property_mapper.register_map(UDM_SCHOOL_PROPERTY_MAPPING)

    # ── Shared fetch helpers ────────────────────────────────────────────────

    async def _dns_to_known_ids(
        self,
        mapper: SQLAlchemyDNIDMapper,
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
        mapper: SQLAlchemyDNIDMapper,
        storage: Any,
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
        mapper: SQLAlchemyDNIDMapper,
        storage: Any,
    ) -> set[Group]:
        known_ids = await self._dns_to_known_ids(mapper, ObjectType.GROUP, dns, label)
        if not known_ids:
            return set()
        return set(
            await storage.groups.search(
                SearchQuery(Filter(field="public_id", op=Operator.IN, value=known_ids))
            )
        )

    async def _fetch_roles_by_entries(self, role_entries: list[str], storage: Any) -> set:
        role_names = {r.split(":")[0] for r in role_entries}
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

    async def _build_school_memberships(
        self,
        schools: list[School],
        groups: set[Group],
        role_entries: list[str],
        storage: Any,
    ) -> dict[UUID, SchoolMembership]:
        all_role_names = {r.split(":")[0] for r in role_entries}
        roles_by_name: dict = {}
        if all_role_names:
            roles_by_name = {
                r.name: r
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
            school_role_names = {r.split(":")[0] for r in role_entries if r.endswith(f":{school.name}")}
            result[school.public_id] = SchoolMembership(
                school,
                groups=set(groups),
                is_primary=True,
                roles={roles_by_name[n] for n in school_role_names if n in roles_by_name},
            )
        return result

    # ── User event handlers ─────────────────────────────────────────────────

    async def handle_user_event(self, user_event: UserEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = SQLAlchemyDNIDMapper(cast(KelvinSqlAlchemySession, storage).session)
            match user_event.event_type:
                case EventType.CREATE:
                    await self._handle_user_create(user_event, storage, mapper)
                case EventType.DELETE:
                    await self._handle_user_delete(user_event, storage)
                case EventType.MODIFY:
                    await self._handle_user_modify(user_event, storage, mapper)

    async def _handle_user_create(
        self, user_event: UserEvent, storage: Any, mapper: SQLAlchemyDNIDMapper
    ) -> None:
        if user_event.new is None:
            return
        props = user_event.new["properties"]
        raw_schools = props["school"]
        logger.debug("User {!r} has school property: {!r}", props.get("username"), raw_schools)
        schools = list(
            await storage.schools.search(
                SearchQuery(
                    Or(clauses=tuple(Filter(field="name", op=Operator.EQ, value=s) for s in raw_schools))
                )
            )
        )
        if not schools:
            logger.warning(
                "School(s) {!r} not found for user {!r}, dropping event",
                raw_schools,
                props.get("username"),
            )
            return
        logger.debug(
            "Found {} school(s) for user {!r}: {!r}",
            len(schools),
            props.get("username"),
            [s.name for s in schools],
        )

        groups = await self._fetch_groups_by_dns(props.get("groups", []), "Group", mapper, storage)
        school_memberships = await self._build_school_memberships(
            schools, groups, props.get("ucsschoolRole", []), storage
        )
        legal_wards = await self._fetch_users_by_dns(
            props.get("ucsschoolLegalWard", []), "Legal ward", mapper, storage
        )
        legal_guardians = await self._fetch_users_by_dns(
            props.get("ucsschoolLegalGuardian", []), "Legal guardian", mapper, storage
        )

        user_kwargs = self.udm_property_mapper.map(props)
        if not user_kwargs.get("record_uid"):
            user_kwargs["record_uid"] = user_kwargs.get("name", "")
        if not user_kwargs.get("source_uid"):
            user_kwargs["source_uid"] = "UMC"
        user_kwargs["school_memberships"] = school_memberships
        user_kwargs["legal_wards"] = legal_wards
        user_kwargs["legal_guardians"] = legal_guardians
        public_id = uuid.UUID(props["univentionObjectIdentifier"])
        await storage.users.create(User(public_id=public_id, **user_kwargs))
        await mapper.set_mapping(ObjectType.USER, user_event.new["dn"], public_id)

    async def _handle_user_delete(self, user_event: UserEvent, storage: Any) -> None:
        if user_event.old is None:
            return
        await storage.users.delete(uuid.UUID(user_event.old["properties"]["univentionObjectIdentifier"]))

    async def _handle_user_modify(
        self, user_event: UserEvent, storage: Any, mapper: SQLAlchemyDNIDMapper
    ) -> None:
        if user_event.new is None:
            return
        props = user_event.new["properties"]
        public_id = uuid.UUID(props["univentionObjectIdentifier"])
        current_user = await storage.users.get(
            public_id,
            load=LoadSpec.from_attributes("school_memberships", "legal_wards", "legal_guardians"),
        )

        school_memberships = await self._maybe_rebuild_school_memberships(props, mapper, storage)
        legal_wards = await self._maybe_fetch_users_for_prop(
            props, "ucsschoolLegalWard", "Legal ward", mapper, storage
        )
        legal_guardians = await self._maybe_fetch_users_for_prop(
            props, "ucsschoolLegalGuardian", "Legal guardian", mapper, storage
        )

        user_kwargs = self.udm_property_mapper.map(props)
        if not user_kwargs.get("record_uid"):
            user_kwargs["record_uid"] = user_kwargs.get("name", "")
        if not user_kwargs.get("source_uid"):
            user_kwargs["source_uid"] = "UMC"

        with track_changes(
            current_user, replace_fields=frozenset({"legal_wards", "legal_guardians"})
        ) as tracker:
            self._apply_user_changes(
                current_user,
                user_kwargs,
                school_memberships,
                legal_wards,
                legal_guardians,
            )
        if tracker.patch:
            await storage.users.modify(public_id, tracker.patch)

    def _apply_user_changes(
        self,
        user: User,
        user_kwargs: dict,
        school_memberships: Any,
        legal_wards: Any,
        legal_guardians: Any,
    ) -> None:
        _membership_fields = frozenset({"school_memberships", "legal_wards", "legal_guardians"})
        for field, value in user_kwargs.items():
            if field not in _membership_fields:
                setattr(user, field, value)
        for field, value in (
            ("school_memberships", school_memberships),
            ("legal_wards", legal_wards),
            ("legal_guardians", legal_guardians),
        ):
            if value is not UNLOADED:
                setattr(user, field, value)

    async def _maybe_rebuild_school_memberships(
        self, props: dict, mapper: SQLAlchemyDNIDMapper, storage: Any
    ) -> dict[UUID, SchoolMembership] | object:
        if not ({"school", "groups", "ucsschoolRole"} & props.keys()):
            return UNLOADED
        schools = list(
            await storage.schools.search(
                SearchQuery(
                    Or(
                        clauses=tuple(
                            Filter(field="name", op=Operator.EQ, value=s)
                            for s in props.get("school", [])
                        )
                    )
                )
            )
        )
        groups = await self._fetch_groups_by_dns(props.get("groups", []), "Group", mapper, storage)
        return await self._build_school_memberships(
            schools, groups, props.get("ucsschoolRole", []), storage
        )

    async def _maybe_fetch_users_for_prop(
        self,
        props: dict,
        prop_key: str,
        label: str,
        mapper: SQLAlchemyDNIDMapper,
        storage: Any,
    ) -> set[User] | object:
        if prop_key not in props:
            return UNLOADED
        return await self._fetch_users_by_dns(props[prop_key], label, mapper, storage)

    # ── Group event handlers ────────────────────────────────────────────────

    async def handle_group_event(self, group_event: GroupEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = SQLAlchemyDNIDMapper(cast(KelvinSqlAlchemySession, storage).session)
            match group_event.event_type:
                case EventType.CREATE:
                    await self._handle_group_create(group_event, storage, mapper)
                case EventType.DELETE:
                    await self._handle_group_delete(group_event, storage)
                case EventType.MODIFY:
                    await self._handle_group_modify(group_event, storage, mapper)

    async def _handle_group_create(
        self, group_event: GroupEvent, storage: Any, mapper: SQLAlchemyDNIDMapper
    ) -> None:
        if group_event.new is None:
            return
        props = group_event.new["properties"]
        group_name = props.get("name", "")
        school_name = group_name.split("-")[0]
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
            props.get("allowedEmailUsers", []), "Email sender user", mapper, storage
        )
        allowed_email_senders_groups = await self._fetch_groups_by_dns(
            props.get("allowedEmailGroups", []), "Email sender group", mapper, storage
        )
        members = await self._fetch_users_by_dns(props.get("users", []), "Member", mapper, storage)
        group_type_roles = await self._fetch_roles_by_entries(props.get("ucsschoolRole", []), storage)

        group_kwargs = self.udm_group_property_mapper.map(props)
        group_kwargs.update(
            {
                "record_uid": group_kwargs["name"],
                "source_uid": "kelvin-connector",
                "display_name": group_kwargs["name"],
                "school": school,
                "allowed_email_senders_users": allowed_email_senders_users,
                "allowed_email_senders_groups": allowed_email_senders_groups,
                "members": members,
                "member_roles": set(),
                "create_share": False,
                "group_type": group_type_roles,
            }
        )
        public_id = uuid.UUID(props["univentionObjectIdentifier"])
        await storage.groups.create(Group(public_id=public_id, **group_kwargs))
        await mapper.set_mapping(ObjectType.GROUP, group_event.new["dn"], public_id)

    async def _handle_group_delete(self, group_event: GroupEvent, storage: Any) -> None:
        if group_event.old is None:
            return
        await storage.groups.delete(
            uuid.UUID(group_event.old["properties"]["univentionObjectIdentifier"])
        )

    async def _handle_group_modify(
        self, group_event: GroupEvent, storage: Any, mapper: SQLAlchemyDNIDMapper
    ) -> None:
        if group_event.new is None:
            return
        props = group_event.new["properties"]
        public_id = uuid.UUID(props["univentionObjectIdentifier"])
        current_group = await storage.groups.get(
            public_id,
            load=LoadSpec.from_attributes(
                "school",
                "group_type",
                "allowed_email_senders_users",
                "allowed_email_senders_groups",
                "members",
            ),
        )

        school = await self._maybe_fetch_school_for_group(props, storage)
        allowed_email_senders_users = await self._maybe_fetch_users_for_prop(
            props, "allowedEmailUsers", "Email sender user", mapper, storage
        )
        allowed_email_senders_groups = await self._maybe_fetch_groups_for_prop(
            props, "allowedEmailGroups", "Email sender group", mapper, storage
        )
        members = await self._maybe_fetch_users_for_prop(props, "users", "Member", mapper, storage)
        group_type_roles = await self._maybe_fetch_group_type_roles(props, storage)

        group_kwargs = self.udm_group_property_mapper.map(props)
        with track_changes(
            current_group,
            replace_fields=frozenset(
                {
                    "school",
                    "group_type",
                    "allowed_email_senders_users",
                    "allowed_email_senders_groups",
                    "members",
                }
            ),
        ) as tracker:
            self._apply_group_changes(
                current_group,
                group_kwargs,
                school,
                group_type_roles,
                allowed_email_senders_users,
                allowed_email_senders_groups,
                members,
            )
        if tracker.patch:
            await storage.groups.modify(public_id, tracker.patch)

    def _apply_group_changes(
        self,
        group: Group,
        group_kwargs: dict,
        school: Any,
        group_type_roles: Any,
        allowed_email_senders_users: Any,
        allowed_email_senders_groups: Any,
        members: Any,
    ) -> None:
        group_name = group_kwargs.get("name")
        if group_name:
            group.name = group_name
            group.display_name = group_name
            group.record_uid = group_name
        if "email" in group_kwargs:
            group.email = group_kwargs["email"]
        for field, value in (
            ("school", school),
            ("group_type", group_type_roles),
            ("allowed_email_senders_users", allowed_email_senders_users),
            ("allowed_email_senders_groups", allowed_email_senders_groups),
            ("members", members),
        ):
            if value is not UNLOADED:
                setattr(group, field, value)

    async def _maybe_fetch_school_for_group(self, props: dict, storage: Any) -> School | object:
        if "name" not in props:
            return UNLOADED
        school_name = props["name"].split("-")[0]
        found = list(
            await storage.schools.search(
                SearchQuery(Filter(field="name", op=Operator.EQ, value=school_name))
            )
        )
        return found[0] if found else UNLOADED

    async def _maybe_fetch_groups_for_prop(
        self,
        props: dict,
        prop_key: str,
        label: str,
        mapper: SQLAlchemyDNIDMapper,
        storage: Any,
    ) -> set[Group] | object:
        if prop_key not in props:
            return UNLOADED
        return await self._fetch_groups_by_dns(props[prop_key], label, mapper, storage)

    async def _maybe_fetch_group_type_roles(self, props: dict, storage: Any) -> set | object:
        if "ucsschoolRole" not in props:
            return UNLOADED
        return await self._fetch_roles_by_entries(props["ucsschoolRole"], storage)

    # ── School event handlers ───────────────────────────────────────────────

    async def handle_school_event(self, school_event: SchoolEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            mapper = SQLAlchemyDNIDMapper(cast(KelvinSqlAlchemySession, storage).session)
            match school_event.event_type:
                case EventType.CREATE:
                    await self._handle_school_create(school_event, storage, mapper)
                case EventType.DELETE:
                    await self._handle_school_delete(school_event, storage)
                case EventType.MODIFY:
                    await self._handle_school_modify(school_event, storage)

    async def _handle_school_create(
        self, school_event: SchoolEvent, storage: Any, mapper: SQLAlchemyDNIDMapper
    ) -> None:
        if school_event.new is None:
            return
        school_kwargs = self.udm_school_property_mapper.map(school_event.new["properties"])
        public_id = uuid.UUID(school_event.new["properties"]["univentionObjectIdentifier"])
        school = School(
            public_id=public_id,
            record_uid=school_kwargs["name"],
            source_uid="kelvin-connector",
            educational_servers={"TODO"},
            administrative_servers={"TODO"},
            **school_kwargs,
        )
        await storage.schools.create(school)
        await mapper.set_mapping(ObjectType.SCHOOL, school_event.new["dn"], public_id)
        logger.info("School {!r} created (public_id={})", school_kwargs["name"], public_id)

    async def _handle_school_delete(self, school_event: SchoolEvent, storage: Any) -> None:
        if school_event.old is None:
            return
        await storage.schools.delete(
            uuid.UUID(school_event.old["properties"]["univentionObjectIdentifier"])
        )

    async def _handle_school_modify(self, school_event: SchoolEvent, storage: Any) -> None:
        if school_event.new is None:
            return
        public_id = uuid.UUID(school_event.new["properties"]["univentionObjectIdentifier"])
        current_school = await storage.schools.get(public_id)
        school_kwargs = self.udm_school_property_mapper.map(school_event.new["properties"])
        with track_changes(current_school) as tracker:
            for field, value in school_kwargs.items():
                setattr(current_school, field, value)
        if tracker.patch:
            await storage.schools.modify(public_id, tracker.patch)
