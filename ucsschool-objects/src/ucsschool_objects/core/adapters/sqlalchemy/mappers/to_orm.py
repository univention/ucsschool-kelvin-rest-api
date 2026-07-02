from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
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
    Group,
    Role,
    School,
    SchoolMembership as DomainSchoolMembership,
    UnloadedType,
    User,
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
        record_uid=data.record_uid,
        source_uid=data.source_uid,
        name=data.name,
        display_name=data.display_name,
        educational_servers=list(data.educational_servers),
        administrative_servers=list(data.administrative_servers),
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
        udm_properties=data.udm_properties,
    )
    if data.is_unset():
        school_model.public_id = generate_public_id()
    else:
        school_model.public_id = data.public_id
    return school_model


def to_role_model(data: Role) -> RoleModel:
    role_model = RoleModel(
        name=data.name,
        display_name=data.display_name,
    )
    if data.is_unset():
        role_model.public_id = generate_public_id()
    else:
        role_model.public_id = data.public_id
    return role_model


def to_group_model(data: Group) -> GroupModel:
    group_model = GroupModel(
        record_uid=data.record_uid,
        source_uid=data.source_uid,
        name=data.name,
        display_name=data.display_name,
        has_share=data.create_share,
        email=check_nullable_value_presence(data.email, object_type="Group", field_name="email"),
        description=check_nullable_value_presence(
            data.description, object_type="Group", field_name="description"
        ),
        udm_properties=data.udm_properties,
    )
    if data.is_unset():
        group_model.public_id = generate_public_id()
    else:
        group_model.public_id = data.public_id
    return group_model


def to_user_model(data: User) -> UserModel:
    user_model = UserModel(
        record_uid=data.record_uid,
        source_uid=data.source_uid,
        name=data.name,
        firstname=data.firstname,
        lastname=data.lastname,
        active=data.active,
        email=check_nullable_value_presence(data.email, object_type="User", field_name="email"),
        birthday=check_nullable_value_presence(data.birthday, object_type="User", field_name="birthday"),
        expiration_date=check_nullable_value_presence(
            data.expiration_date,
            object_type="User",
            field_name="expiration_date",
        ),
        udm_properties=data.udm_properties,
    )
    if data.is_unset():
        user_model.public_id = generate_public_id()
    else:
        user_model.public_id = data.public_id
    return user_model


def _extract_related_public_ids(references: Iterable[PublicIdCarrier]) -> list[UUID]:
    return [reference.public_id for reference in references]


async def resolve_group_create_relations(
    session: AsyncSession,
    data: Group,
) -> GroupCreateRelations:
    group_role_ids = [r.public_id for r in data.roles if not r.is_unset()]
    group_roles_by_id = await bulk_fetch_by_public_id(session, RoleModel, group_role_ids, "Role")

    school_model = await fetch_one_by_public_id(session, SchoolModel, data.school.public_id, "School")

    member_user_public_ids = _extract_related_public_ids(data.members)
    member_users_by_id = await bulk_fetch_by_public_id(
        session, UserModel, member_user_public_ids, "User"
    )
    membership_models = await _resolve_group_member_memberships(
        session,
        member_users_by_id,
        school_model,
    )

    role_ids = [role.public_id for role in data.member_roles]
    roles_by_id = await bulk_fetch_by_public_id(session, RoleModel, role_ids, "Role")

    sender_user_public_ids = _extract_related_public_ids(data.allowed_email_senders_users)
    users_by_id = await bulk_fetch_by_public_id(session, UserModel, sender_user_public_ids, "User")

    sender_group_public_ids = _extract_related_public_ids(data.allowed_email_senders_groups)
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

    public_ids = [user.public_id for user in users]
    users_by_id = await bulk_fetch_by_public_id(session, UserModel, public_ids, "User")
    return list(users_by_id.values())


def _validate_membership_entry(
    membership_school_id: UUID,
    membership: DomainSchoolMembership,
) -> tuple[UUID, list[UUID], list[UUID]]:
    school_id = membership.school.public_id
    if membership_school_id != school_id:
        raise ValueError("school_memberships keys must match membership school public_id.")

    membership_role_ids = [role.public_id for role in membership.roles]
    membership_group_ids = [group.public_id for group in membership.groups]

    return school_id, membership_role_ids, membership_group_ids


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
