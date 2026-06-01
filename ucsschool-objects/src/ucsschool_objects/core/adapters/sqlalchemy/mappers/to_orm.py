from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import select
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    bulk_fetch_by_public_id,
    check_nullable_value_presence,
    fetch_one_by_public_id,
    generate_public_id,
)
from ucsschool_objects.core.domain.errors import NotFound
from ucsschool_objects.core.domain.models import (
    UNLOADED,
    UNSET,
    Group,
    Role,
    School,
    SchoolMembership as DomainSchoolMembership,
    UnloadedType,
    User,
    _require_loaded,
    is_loaded,
)
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession
    from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import PublicIdCarrier


@dataclass(frozen=True)
class GroupCreateRelations:
    roles: list[RoleModel]
    school: SchoolModel
    member_roles: list[RoleModel]
    members: list[SchoolMembershipModel]
    allowed_email_senders_users: list[UserModel]
    allowed_email_senders_groups: list[GroupModel]


@dataclass(frozen=True)
class UserCreateRelations:
    school_memberships: list[SchoolMembershipModel]
    legal_wards: list[UserModel] | None
    legal_guardians: list[UserModel] | None


def to_school_model(data: School) -> SchoolModel:
    school_model = SchoolModel(
        record_uid=_require_loaded(data.record_uid, object_type="School", field_name="record_uid"),
        source_uid=_require_loaded(data.source_uid, object_type="School", field_name="source_uid"),
        name=_require_loaded(data.name, object_type="School", field_name="name"),
        display_name=_require_loaded(data.display_name, object_type="School", field_name="display_name"),
        educational_servers=list(
            _require_loaded(
                data.educational_servers,
                object_type="School",
                field_name="educational_servers",
            ),
        ),
        administrative_servers=list(
            _require_loaded(
                data.administrative_servers,
                object_type="School",
                field_name="administrative_servers",
            )
        ),
        class_share_file_server=check_nullable_value_presence(
            data.class_share_file_server,
            object_type="School",
            field_name="class_share_file_server",
        ),
        home_share_file_server=check_nullable_value_presence(
            data.home_share_file_server,
            object_type="School",
            field_name="home_share_file_server",
        ),
    )
    if isinstance(data.public_id, UUID):
        school_model.public_id = data.public_id
    return school_model


def to_role_model(data: Role) -> RoleModel:
    role_model = RoleModel(
        name=_require_loaded(data.name, object_type="Role", field_name="name"),
        display_name=_require_loaded(data.display_name, object_type="Role", field_name="display_name"),
    )
    if data.public_id == UNSET:
        role_model.public_id = generate_public_id()
    else:
        role_model.public_id = cast(UUID, data.public_id)
    return role_model


def to_group_model(data: Group) -> GroupModel:
    group_model = GroupModel(
        record_uid=_require_loaded(data.record_uid, object_type="Group", field_name="record_uid"),
        source_uid=_require_loaded(data.source_uid, object_type="Group", field_name="source_uid"),
        name=_require_loaded(data.name, object_type="Group", field_name="name"),
        display_name=_require_loaded(data.display_name, object_type="Group", field_name="display_name"),
        has_share=_require_loaded(data.create_share, object_type="Group", field_name="create_share"),
        email=check_nullable_value_presence(data.email, object_type="Group", field_name="email"),
    )
    if data.public_id == UNSET:
        group_model.public_id = generate_public_id()
    else:
        group_model.public_id = cast(UUID, data.public_id)
    return group_model


def to_user_model(data: User) -> UserModel:
    user_model = UserModel(
        record_uid=_require_loaded(data.record_uid, object_type="User", field_name="record_uid"),
        source_uid=_require_loaded(data.source_uid, object_type="User", field_name="source_uid"),
        name=_require_loaded(data.name, object_type="User", field_name="name"),
        firstname=_require_loaded(data.firstname, object_type="User", field_name="firstname"),
        lastname=_require_loaded(data.lastname, object_type="User", field_name="lastname"),
        active=_require_loaded(data.active, object_type="User", field_name="active"),
        email=check_nullable_value_presence(data.email, object_type="User", field_name="email"),
        birthday=check_nullable_value_presence(data.birthday, object_type="User", field_name="birthday"),
        expiration_date=check_nullable_value_presence(
            data.expiration_date,
            object_type="User",
            field_name="expiration_date",
        ),
    )
    if isinstance(data.public_id, UUID):
        user_model.public_id = data.public_id
    return user_model


def _extract_related_public_ids(
    references: Iterable[PublicIdCarrier],
    *,
    owner_name: str,
    related_type: str,
) -> list[UUID]:
    public_ids: list[UUID] = []
    for reference in references:
        public_id = _require_loaded(
            reference.public_id,
            object_type=related_type,
            field_name="public_id",
        )
        if not isinstance(public_id, UUID):
            raise ValueError(f"{owner_name} entries must have a public_id.")
        public_ids.append(public_id)
    return public_ids


async def resolve_group_create_relations(
    session: AsyncSession,
    data: Group,
) -> GroupCreateRelations:
    group_roles = _require_loaded(data.roles, object_type="Group", field_name="roles")
    group_role_ids = [r.public_id for r in group_roles if isinstance(r.public_id, UUID)]
    group_roles_by_id = await bulk_fetch_by_public_id(session, RoleModel, group_role_ids, "Role")

    school = _require_loaded(data.school, object_type="Group", field_name="school")
    if not isinstance(school.public_id, UUID):
        raise ValueError("Group.school must have a public_id for create().")
    school_model = await fetch_one_by_public_id(session, SchoolModel, school.public_id, "School")

    members = _require_loaded(data.members, object_type="Group", field_name="members")
    member_user_public_ids = _extract_related_public_ids(
        members,
        owner_name="Group.members",
        related_type="User",
    )
    member_users_by_id = await bulk_fetch_by_public_id(
        session, UserModel, member_user_public_ids, "User"
    )
    membership_models = await _resolve_group_member_memberships(
        session,
        member_users_by_id,
        school_model,
    )

    member_roles = _require_loaded(data.member_roles, object_type="Group", field_name="member_roles")
    role_ids = [role.public_id for role in member_roles if isinstance(role.public_id, UUID)]
    roles_by_id = await bulk_fetch_by_public_id(session, RoleModel, role_ids, "Role")

    allowed_email_senders_users = _require_loaded(
        data.allowed_email_senders_users,
        object_type="Group",
        field_name="allowed_email_senders_users",
    )
    sender_user_public_ids = _extract_related_public_ids(
        allowed_email_senders_users,
        owner_name="Group.allowed_email_senders_users",
        related_type="User",
    )
    users_by_id = await bulk_fetch_by_public_id(session, UserModel, sender_user_public_ids, "User")

    allowed_email_senders_groups = _require_loaded(
        data.allowed_email_senders_groups,
        object_type="Group",
        field_name="allowed_email_senders_groups",
    )
    sender_group_public_ids = _extract_related_public_ids(
        allowed_email_senders_groups,
        owner_name="Group.allowed_email_senders_groups",
        related_type="Group",
    )
    groups_by_id = await bulk_fetch_by_public_id(session, GroupModel, sender_group_public_ids, "Group")

    return GroupCreateRelations(
        roles=list(group_roles_by_id.values()),
        school=school_model,
        member_roles=list(roles_by_id.values()),
        members=membership_models,
        allowed_email_senders_users=list(users_by_id.values()),
        allowed_email_senders_groups=list(groups_by_id.values()),
    )


async def _resolve_group_member_memberships(
    session: AsyncSession,
    users_by_public_id: dict[UUID, UserModel],
    school_model: SchoolModel,
) -> list[SchoolMembershipModel]:
    if not users_by_public_id:
        return []

    member_user_ids = [user.id for user in users_by_public_id.values()]
    memberships = (
        (
            await session.execute(
                select(SchoolMembershipModel).where(
                    SchoolMembershipModel.user_id.in_(member_user_ids),
                    SchoolMembershipModel.school_id == school_model.id,
                )
            )
        )
        .scalars()
        .all()
    )
    by_user_id: dict[int, SchoolMembershipModel] = {
        membership.user_id: membership for membership in memberships
    }
    result: list[SchoolMembershipModel] = []
    for user in users_by_public_id.values():
        if user.id not in by_user_id:
            raise NotFound(
                object_type="SchoolMembership",
                public_id=f"user={user.public_id}, school={school_model.public_id}",
            )
        result.append(by_user_id[user.id])
    return result


async def resolve_user_create_relations(
    session: AsyncSession,
    data: User,
) -> UserCreateRelations:
    school_memberships = data.school_memberships if is_loaded(data, "school_memberships") else UNLOADED
    legal_wards = data.legal_wards if is_loaded(data, "legal_wards") else UNLOADED
    legal_guardians = data.legal_guardians if is_loaded(data, "legal_guardians") else UNLOADED

    return UserCreateRelations(
        school_memberships=await _build_memberships(session, school_memberships),
        legal_wards=await _resolve_related_users(session, legal_wards),
        legal_guardians=await _resolve_related_users(session, legal_guardians),
    )


async def _resolve_related_users(
    session: AsyncSession,
    users: set[User] | UnloadedType,
) -> list[UserModel] | None:
    if isinstance(users, UnloadedType):
        return None

    public_ids = [user.public_id for user in users if isinstance(user.public_id, UUID)]
    users_by_id = await bulk_fetch_by_public_id(session, UserModel, public_ids, "User")
    return list(users_by_id.values())


def _membership_school_id(membership: DomainSchoolMembership) -> UUID:
    school = membership.school
    if isinstance(school, UnloadedType) or not isinstance(school.public_id, UUID):
        raise ValueError("All membership schools must be loaded with public_id for create().")
    return school.public_id


def _membership_role_ids(membership: DomainSchoolMembership) -> list[UUID]:
    role_ids: list[UUID] = []
    for role in membership.roles:
        if not isinstance(role.public_id, UUID):
            raise ValueError("All membership roles must provide public_id for create().")
        role_ids.append(role.public_id)
    return role_ids


def _membership_group_ids(membership: DomainSchoolMembership) -> list[UUID]:
    group_ids: list[UUID] = []
    for group in membership.groups:
        if not isinstance(group.public_id, UUID):
            raise ValueError("All membership groups must provide public_id for create().")
        group_ids.append(group.public_id)
    return group_ids


def _validate_membership_entry(
    membership_school_id: UUID,
    membership: DomainSchoolMembership,
) -> tuple[UUID, list[UUID], list[UUID]]:
    school_id = _membership_school_id(membership)
    if membership_school_id != school_id:
        raise ValueError("school_memberships keys must match membership school public_id.")
    return school_id, _membership_role_ids(membership), _membership_group_ids(membership)


async def _build_memberships(
    session: AsyncSession,
    memberships: dict[UUID, DomainSchoolMembership] | UnloadedType,
) -> list[SchoolMembershipModel]:
    if isinstance(memberships, UnloadedType):
        return []

    validated: list[tuple[DomainSchoolMembership, UUID, list[UUID], list[UUID]]] = []
    school_ids: list[UUID] = []
    all_role_ids: list[UUID] = []
    all_group_ids: list[UUID] = []
    for membership_school_id, membership in memberships.items():
        school_id, role_ids, group_ids = _validate_membership_entry(membership_school_id, membership)

        validated.append((membership, school_id, role_ids, group_ids))
        school_ids.append(school_id)
        all_role_ids.extend(role_ids)
        all_group_ids.extend(group_ids)

    schools_by_id = await bulk_fetch_by_public_id(session, SchoolModel, school_ids, "School")
    roles_by_id = await bulk_fetch_by_public_id(session, RoleModel, all_role_ids, "Role")
    groups_by_id = await bulk_fetch_by_public_id(session, GroupModel, all_group_ids, "Group")

    membership_models: list[SchoolMembershipModel] = []
    for membership, school_id, role_ids, group_ids in validated:
        membership_model = SchoolMembershipModel(
            is_primary=membership.is_primary,
            school=schools_by_id[school_id],
        )
        membership_model.roles = [roles_by_id[role_id] for role_id in role_ids]
        membership_model.groups = [groups_by_id[group_id] for group_id in group_ids]
        membership_models.append(membership_model)

    return membership_models
