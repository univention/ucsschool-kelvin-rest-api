from typing import Any, Callable, final
from uuid import UUID

from kelvin_connector.models import (
    EventType,
    GroupEvent,
    SchoolEvent,
    UserEvent,
)
from kelvin_connector.ports import SynchronizationManagerProtocol
from ucsschool_objects.core.domain import SearchQuery
from ucsschool_objects.core.domain.models import SchoolMembership, UnsetType, User
from ucsschool_objects.core.domain.ports import KelvinStorageSessionFactory
from ucsschool_objects.core.domain.query import (
    Filter,
    Operator,
    Or,
)

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
}

UDM_SCHOOL_PROPERTY_MAPPING = {
    "name": "name",
    "displayName": "display_name",
    "ucsschoolHomeShareFileServer": "home_share_file_server",
    "ucsschoolClassShareFileServer": "class_share_file_server",
    # TODO
    # educational_servers
    # administrative_servers
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

    def register(self, source_key: str, target_key: str) -> None:
        """Register a 1:1 mapping between source and target keys."""
        if source_key in self._mappings:
            raise ValueError(f"Source key '{source_key}' is already registered.")
        if target_key in self._mappings.values():
            raise ValueError(f"Target key '{target_key}' is already registered.")
        self._mappings[source_key] = target_key

    def register_hook(self, source_key: str, func: Callable[..., Any]):
        """Register a hook function for a source key to transform its value."""
        if source_key not in self._mappings:
            raise ValueError(f"Source key '{source_key}' is not registered.")

        self._hooks[source_key] = func

    def map(self, source: dict[str, Any]) -> dict[str, Any]:
        """Map source dictionary to a new dictionary using registered mappings."""
        result = {}

        for source_key, target_key in self._mappings.items():
            if source_key not in source:
                continue

            target_key = self._mappings[source_key]
            value = source[source_key]

            if source_key in self._hooks:
                value = self._hooks[source_key](value)

            result[target_key] = value

        return result


class UDMPropertyRelationMapper:
    pass


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

    async def handle_user_event(self, user_event: UserEvent) -> None:
        async with self.storage_factory.transaction_scope() as storage:
            match user_event.event_type:
                case EventType.CREATE:
                    if user_event.new is None:
                        return
                    school_memberships: dict[UUID, SchoolMembership] = dict()

                    school_search_query = SearchQuery(
                        Or(
                            clauses=tuple(
                                Filter(field="name", op=Operator.EQ, value=school_name)
                                for school_name in user_event.new["properties"]["school"]
                            )
                        )
                    )
                    schools = await storage.schools.search(school_search_query)

                    for school in schools:
                        role_search_query = SearchQuery(
                            Or(
                                clauses=tuple(
                                    Filter(field="name", op=Operator.EQ, value=role.split(":")[0])
                                    for role in user_event.new["properties"]["ucsschoolRole"]
                                    if role.endswith(f":{school.name}")
                                )
                            )
                        )
                        roles = await storage.roles.search(role_search_query)

                        # TODO school specific groups
                        group_search_query = SearchQuery(
                            Or(
                                clauses=tuple(
                                    Filter(field="name", op=Operator.EQ, value=group)
                                    for group in user_event.new["properties"]["groups"]
                                )
                            )
                        )
                        groups = await storage.groups.search(group_search_query)
                        assert not isinstance(school.public_id, UnsetType)
                        school_memberships[school.public_id] = SchoolMembership(
                            school, groups=set(groups), is_primary=True, roles=set(roles)
                        )
                    user_keyword_arguments = self.udm_property_mapper.map(user_event.new["properties"])
                    user = User(
                        public_id=user_event.new["id"],
                        school_memberships=school_memberships,
                        **user_keyword_arguments,
                    )
                    await storage.users.create(user)
                case EventType.DELETE:
                    if user_event.old is None:
                        return
                    await storage.users.delete(user_event.old["id"])
                case EventType.MODIFY:
                    pass

    async def handle_group_event(self, group_event: GroupEvent) -> None:
        match group_event.event_type:
            case EventType.CREATE:
                pass
            case EventType.DELETE:
                pass
            case EventType.MODIFY:
                pass

    async def handle_school_event(self, school_event: SchoolEvent) -> None:
        match school_event.event_type:
            case EventType.CREATE:
                pass
            case EventType.DELETE:
                pass
            case EventType.MODIFY:
                pass
