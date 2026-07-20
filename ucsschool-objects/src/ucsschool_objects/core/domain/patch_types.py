from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias, TypedDict, TypeVar, cast

from ucsschool_objects.core.domain.errors import PatchShapeMismatch

PublicIdPatchDict: TypeAlias = dict[str, object]

T = TypeVar("T", bound=Mapping[str, object])


def as_patch_dict(data: Mapping[str, object], patch_type: type[T]) -> T:
    """Verify `data` carries every key `patch_type` requires, then return it typed as `patch_type`.

    `data` is the full serialized domain object (e.g. it also carries `public_id`),
    a superset of the patch dict's fields, so only missing required keys are an error.
    """
    required: frozenset[str] = getattr(patch_type, "__required_keys__", frozenset())
    missing = required - data.keys()
    if missing:
        raise PatchShapeMismatch(patch_type=patch_type.__name__, missing_keys=frozenset(missing))
    return cast(T, data)


class SchoolPatchDict(TypedDict, total=False):
    record_uid: str
    source_uid: str
    name: str
    display_name: str
    educational_servers: list[str]
    administrative_servers: list[str]
    class_share_file_server: str | None
    home_share_file_server: str | None
    udm_properties: dict[str, object]


class GroupPatchDict(TypedDict, total=False):
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


class UserPatchDict(TypedDict, total=False):
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
