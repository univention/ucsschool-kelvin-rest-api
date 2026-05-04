from typing import Any, Callable

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
    "guardianMemberRoles": "member_roles",
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
