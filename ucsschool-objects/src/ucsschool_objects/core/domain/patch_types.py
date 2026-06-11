from __future__ import annotations

from typing import TypeAlias, TypedDict

PublicIdPatchDict: TypeAlias = dict[str, object]


class SchoolPatchDict(TypedDict):
    record_uid: str
    source_uid: str
    name: str
    display_name: str
    educational_servers: list[str]
    administrative_servers: list[str]
    class_share_file_server: str | None
    home_share_file_server: str | None
    udm_properties: dict[str, object]


class GroupPatchDict(TypedDict):
    record_uid: str
    source_uid: str
    name: str
    display_name: str
    create_share: bool
    roles: object
    email: str | None
    description: str | None
    school: PublicIdPatchDict | None
    members: list[PublicIdPatchDict]
    member_roles: list[PublicIdPatchDict]
    allowed_email_senders_users: list[PublicIdPatchDict]
    allowed_email_senders_groups: list[PublicIdPatchDict]
    udm_properties: dict[str, object]


class MembershipPatchDict(TypedDict, total=False):
    groups: list[PublicIdPatchDict]
    roles: list[PublicIdPatchDict]
    is_primary: bool


class UserPatchDict(TypedDict):
    record_uid: str
    source_uid: str
    name: str
    firstname: str
    lastname: str
    email: str | None
    active: bool
    birthday: str | None
    expiration_date: str | None
    udm_properties: dict[str, object]
    school_memberships: dict[str, MembershipPatchDict]
    legal_wards: list[PublicIdPatchDict]
    legal_guardians: list[PublicIdPatchDict]
