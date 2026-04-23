from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    _bulk_fetch_by_public_id,
    _check_nullable_value_presence,
    _check_value_presence,
    _fetch_one_by_name,
    _fetch_one_by_public_id,
    generate_public_id,
)
from ucsschool_objects.core.domain import UNSET, Group, Role, School, UnloadedType, User
from ucsschool_objects.core.domain.models import SchoolMembership as DomainSchoolMembership
from ucsschool_objects.database_models import (
    Group as GroupModel,
    GroupType as GroupTypeModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)


@dataclass(frozen=True)
class GroupCreateRelations:
    group_type: GroupTypeModel
    school: SchoolModel
    member_roles: list[RoleModel]
    allowed_email_senders_users: list[UserModel]
    allowed_email_senders_groups: list[GroupModel]


@dataclass(frozen=True)
class UserCreateRelations:
    school_memberships: list[SchoolMembershipModel]
    legal_wards: list[UserModel] | None
    legal_guardians: list[UserModel] | None


def to_school_model(data: School) -> SchoolModel:
    school_model = SchoolModel(
        record_uid=_check_value_presence(data.record_uid, object_type="School", field_name="record_uid"),
        source_uid=_check_value_presence(data.source_uid, object_type="School", field_name="source_uid"),
        name=_check_value_presence(data.name, object_type="School", field_name="name"),
        display_name=dict(
            _check_value_presence(data.display_name, object_type="School", field_name="display_name"),
        ),
        educational_servers=list(
            _check_value_presence(
                data.educational_servers,
                object_type="School",
                field_name="educational_servers",
            ),
        ),
        administrative_servers=list(
            _check_value_presence(
                data.administrative_servers,
                object_type="School",
                field_name="administrative_servers",
            )
        ),
        class_share_file_server=_check_nullable_value_presence(
            data.class_share_file_server,
            object_type="School",
            field_name="class_share_file_server",
        ),
        home_share_file_server=_check_nullable_value_presence(
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
        name=_check_value_presence(data.name, object_type="Role", field_name="name"),
        display_name=_check_value_presence(
            data.display_name, object_type="Role", field_name="display_name"
        ),
    )
    if data.public_id == UNSET:
        role_model.public_id = generate_public_id()
    else:
        role_model.public_id = cast(UUID, data.public_id)
    return role_model


def to_group_model(data: Group) -> GroupModel:
    group_model = GroupModel(
        record_uid=_check_value_presence(data.record_uid, object_type="Group", field_name="record_uid"),
        source_uid=_check_value_presence(data.source_uid, object_type="Group", field_name="source_uid"),
        name=_check_value_presence(data.name, object_type="Group", field_name="name"),
        display_name=dict(
            _check_value_presence(data.display_name, object_type="Group", field_name="display_name"),
        ),
        has_share=_check_value_presence(
            data.create_share, object_type="Group", field_name="create_share"
        ),
        email=_check_nullable_value_presence(data.email, object_type="Group", field_name="email"),
    )
    if data.public_id == UNSET:
        group_model.public_id = generate_public_id()
    else:
        group_model.public_id = cast(UUID, data.public_id)
    return group_model


def to_user_model(data: User) -> UserModel:
    user_model = UserModel(
        record_uid=_check_value_presence(data.record_uid, object_type="User", field_name="record_uid"),
        source_uid=_check_value_presence(data.source_uid, object_type="User", field_name="source_uid"),
        name=_check_value_presence(data.name, object_type="User", field_name="name"),
        firstname=_check_value_presence(data.firstname, object_type="User", field_name="firstname"),
        lastname=_check_value_presence(data.lastname, object_type="User", field_name="lastname"),
        active=_check_value_presence(data.active, object_type="User", field_name="active"),
        email=_check_nullable_value_presence(data.email, object_type="User", field_name="email"),
        birthday=_check_nullable_value_presence(
            data.birthday, object_type="User", field_name="birthday"
        ),
        expiration_date=_check_nullable_value_presence(
            data.expiration_date,
            object_type="User",
            field_name="expiration_date",
        ),
    )
    if isinstance(data.public_id, UUID):
        user_model.public_id = data.public_id
    return user_model


def _extract_related_public_ids(
    references: Iterable[object],
    *,
    owner_name: str,
    related_type: str,
) -> list[UUID]:
    public_ids: list[UUID] = []
    for reference in references:
        public_id = _check_value_presence(
            getattr(reference, "public_id"), object_type=related_type, field_name="public_id"
        )
        if not isinstance(public_id, UUID):
            raise ValueError(f"{owner_name} entries must have a public_id.")
        public_ids.append(public_id)
    return public_ids


async def resolve_group_create_relations(
    session: AsyncSession,
    data: Group,
) -> GroupCreateRelations:
    group_type_name = _check_value_presence(
        data.group_type, object_type="Group", field_name="group_type"
    )
    group_type = await _fetch_one_by_name(
        session, GroupTypeModel, GroupTypeModel.name, group_type_name, "GroupType"
    )

    school = _check_value_presence(data.school, object_type="Group", field_name="school")
    if not isinstance(school.public_id, UUID):
        raise ValueError("Group.school must have a public_id for create().")
    school_model = await _fetch_one_by_public_id(session, SchoolModel, school.public_id, "School")

    member_roles = _check_value_presence(
        data.member_roles, object_type="Group", field_name="member_roles"
    )
    role_ids = [role.public_id for role in member_roles if isinstance(role.public_id, UUID)]
    roles_by_id = await _bulk_fetch_by_public_id(session, RoleModel, role_ids, "Role")

    allowed_email_senders_users = _check_value_presence(
        data.allowed_email_senders_users,
        object_type="Group",
        field_name="allowed_email_senders_users",
    )
    sender_user_public_ids = _extract_related_public_ids(
        allowed_email_senders_users,
        owner_name="Group.allowed_email_senders_users",
        related_type="User",
    )
    users_by_id = await _bulk_fetch_by_public_id(session, UserModel, sender_user_public_ids, "User")

    allowed_email_senders_groups = _check_value_presence(
        data.allowed_email_senders_groups,
        object_type="Group",
        field_name="allowed_email_senders_groups",
    )
    sender_group_public_ids = _extract_related_public_ids(
        allowed_email_senders_groups,
        owner_name="Group.allowed_email_senders_groups",
        related_type="Group",
    )
    groups_by_id = await _bulk_fetch_by_public_id(session, GroupModel, sender_group_public_ids, "Group")

    return GroupCreateRelations(
        group_type=group_type,
        school=school_model,
        member_roles=list(roles_by_id.values()),
        allowed_email_senders_users=list(users_by_id.values()),
        allowed_email_senders_groups=list(groups_by_id.values()),
    )


async def resolve_user_create_relations(
    session: AsyncSession,
    data: User,
) -> UserCreateRelations:
    return UserCreateRelations(
        school_memberships=await _build_memberships(session, data.school_memberships),
        legal_wards=await _resolve_related_users(session, data.legal_wards),
        legal_guardians=await _resolve_related_users(session, data.legal_guardians),
    )


async def _resolve_related_users(
    session: AsyncSession,
    users: set[User] | UnloadedType,
) -> list[UserModel] | None:
    if isinstance(users, UnloadedType):
        return None

    public_ids = [user.public_id for user in users if isinstance(user.public_id, UUID)]
    users_by_id = await _bulk_fetch_by_public_id(session, UserModel, public_ids, "User")
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

    schools_by_id = await _bulk_fetch_by_public_id(session, SchoolModel, school_ids, "School")
    roles_by_id = await _bulk_fetch_by_public_id(session, RoleModel, all_role_ids, "Role")
    groups_by_id = await _bulk_fetch_by_public_id(session, GroupModel, all_group_ids, "Group")

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
