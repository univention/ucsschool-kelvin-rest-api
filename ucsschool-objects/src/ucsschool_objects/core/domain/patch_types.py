from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias, TypedDict, TypeVar, cast

from ucsschool_objects.core.domain.errors import PatchShapeMismatch

PublicIdPatchDict: TypeAlias = dict[str, object]

T = TypeVar("T", bound=Mapping[str, object])


def as_patch_dict(data: Mapping[str, object], patch_type: type[T]) -> T:
    """Verify `data`'s keys exactly match `patch_type`'s shape, then return it typed as `patch_type`.

    Every key required by `patch_type` must be present, and every key in `data` must be a field
    defined on `patch_type` — unknown keys (e.g. typos) are rejected rather than silently ignored.
    """
    required: frozenset[str] = getattr(patch_type, "__required_keys__", frozenset())
    optional: frozenset[str] = getattr(patch_type, "__optional_keys__", frozenset())
    allowed = required | optional
    missing = required - data.keys()
    undefined = data.keys() - allowed
    if missing or undefined:
        raise PatchShapeMismatch(
            patch_type=patch_type.__name__,
            missing_keys=frozenset(missing),
            undefined_keys=frozenset(undefined),
        )
    return cast(T, data)


class SchoolPatchDict(TypedDict, total=False):
    public_id: str
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
    public_id: str
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
    public_id: str
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
