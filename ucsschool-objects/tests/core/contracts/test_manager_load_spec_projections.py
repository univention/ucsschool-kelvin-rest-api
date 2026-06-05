from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal, TypeVar

import pytest
from ucsschool_objects import (
    Filter,
    Group,
    LoadSpec,
    Operator,
    Role,
    School,
    SearchQuery,
    UnloadedType,
    User,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupManager,
    SQLAlchemyRoleManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.domain.json import _UNLOADED_MARKER, to_json

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncGroupFactory as GroupFactory,
        AsyncGroupTypeFactory as GroupTypeFactory,
        AsyncRoleFactory as RoleFactory,
        AsyncSchoolFactory as SchoolFactory,
        AsyncSchoolMembershipFactory as SchoolMembershipFactory,
        AsyncUserFactory as UserFactory,
    )
    from ucsschool_objects.core.domain.ports.manager import Manager


SCHOOL_LOAD_ATTRS = (
    "record_uid",
    "source_uid",
    "name",
    "class_share_file_server",
    "home_share_file_server",
)
ROLE_LOAD_ATTRS = ("name", "display_name")
GROUP_LOAD_ATTRS = (
    "record_uid",
    "source_uid",
    "name",
    "display_name",
    "create_share",
    "email",
    "roles",
    "allowed_email_senders_users",
    "allowed_email_senders_groups",
    "members",
    "member_roles",
    "school",
)
USER_LOAD_ATTRS = (
    "record_uid",
    "source_uid",
    "name",
    "firstname",
    "lastname",
    "email",
    "birthday",
    "expiration_date",
    "active",
    "school_memberships",
    "primary_school",
    "groups",
    "roles",
    "legal_wards",
    "legal_guardians",
)
USER_MEMBERSHIP_TRIGGERS = frozenset({"school_memberships", "primary_school", "groups", "roles"})

METHODS = ("get", "search")
DomainRecord = TypeVar("DomainRecord", School, Role, Group, User)


def _assert_only_expected_fields_loaded(
    record: School | Role | Group | User, expected_loaded: set[str]
) -> None:
    for field_name, value in to_json(record).items():
        if field_name == "public_id":
            continue
        if field_name in expected_loaded:
            assert value != _UNLOADED_MARKER, field_name
        else:
            assert value == _UNLOADED_MARKER, field_name
            with pytest.raises(
                ValueError, match=rf"{type(record).__name__}\.{field_name} is not loaded"
            ):
                getattr(record, field_name)


def _expected_user_loaded_fields(load_attr: str) -> set[str]:
    if load_attr in USER_MEMBERSHIP_TRIGGERS:
        return {"school_memberships"}
    return {load_attr}


async def _fetch_loaded_record(
    manager: Manager[DomainRecord],
    public_id: UUID,
    query: SearchQuery,
    spec: LoadSpec,
    method_name: Literal["get", "search"],
) -> DomainRecord:
    if method_name == "get":
        return await manager.get(public_id, load=spec)

    result = list(await manager.search(query, load=spec))
    assert len(result) == 1
    return result[0]


async def _setup_school_case(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
) -> tuple[SQLAlchemySchoolManager, UUID, SearchQuery, dict[str, object]]:
    school = await school_factory(
        name="projection-school",
        record_uid="school-record-uid",
        source_uid="school-source-uid",
        class_share_file_server="class-server",
        home_share_file_server="home-server",
    )
    db_session.expunge_all()
    return (
        SQLAlchemySchoolManager(db_session),
        school.public_id,
        SearchQuery(where=Filter(field="name", op=Operator.EQ, value="projection-school")),
        {
            "name": "projection-school",
            "record_uid": "school-record-uid",
            "source_uid": "school-source-uid",
            "class_share_file_server": "class-server",
            "home_share_file_server": "home-server",
        },
    )


async def _setup_role_case(
    db_session: AsyncSession,
    role_factory: RoleFactory,
) -> tuple[SQLAlchemyRoleManager, UUID, SearchQuery, dict[str, object]]:
    role = await role_factory(name="projection:role", display_name={"en": "Role EN"})
    db_session.expunge_all()
    return (
        SQLAlchemyRoleManager(db_session),
        role.public_id,
        SearchQuery(where=Filter(field="name", op=Operator.EQ, value="projection:role")),
        {
            "name": "projection:role",
            "display_name": {"en": "Role EN"},
        },
    )


async def _setup_group_case(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
    user_factory: UserFactory,
    role_factory: RoleFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> tuple[SQLAlchemyGroupManager, UUID, SearchQuery, dict[str, object]]:
    school = await school_factory(name="projection-group-school")
    group_type_role = await roles_factory(name="projection-group-type")
    sender_user = await user_factory(name="sender-user")
    member_user = await user_factory(name="member-user")
    sender_group = await group_factory(name="sender-group", school=school, roles=group_type_role)
    member_role = await role_factory(name="projection-member-role")
    group = await group_factory(
        name="projection-group",
        school=school,
        roles=group_type_role,
        has_share=True,
        email="projection-group@example.org",
    )
    await db_session.refresh(
        group,
        attribute_names=[
            "allowed_email_senders_users",
            "allowed_email_senders_groups",
            "members",
            "member_roles",
        ],
    )
    member_membership = await school_membership_factory(user=member_user, school=school, is_primary=True)
    group.allowed_email_senders_users.append(sender_user)
    group.allowed_email_senders_groups.append(sender_group)
    group.members.append(member_membership)
    group.member_roles.append(member_role)
    await db_session.flush()
    db_session.expunge_all()

    return (
        SQLAlchemyGroupManager(db_session),
        group.public_id,
        SearchQuery(where=Filter(field="name", op=Operator.EQ, value="projection-group")),
        {
            "name": "projection-group",
            "record_uid": group.record_uid,
            "source_uid": group.source_uid,
            "display_name": group.display_name,
            "create_share": True,
            "email": "projection-group@example.org",
            "roles": {"projection-group-type"},
            "sender_user": "sender-user",
            "sender_group": "sender-group",
            "member_user": "member-user",
            "member_role": "projection-member-role",
            "school_name": "projection-group-school",
        },
    )


async def _setup_user_case(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
    role_factory: RoleFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> tuple[SQLAlchemyUserManager, UUID, SearchQuery, dict[str, object]]:
    school = await school_factory(name="projection-user-school")
    group_type_role = await roles_factory(name="projection-user-group-type")
    group = await group_factory(name="projection-user-group", school=school, roles=group_type_role)
    role = await role_factory(name="projection-user-role")
    guardian = await user_factory(name="projection-guardian")
    ward = await user_factory(name="projection-ward")
    user = await user_factory(
        name="projection-user",
        firstname="Projection",
        lastname="User",
        email="projection-user@example.org",
        record_uid="user-record-uid",
        source_uid="user-source-uid",
        birthday=date(2010, 1, 1),
        expiration_date=date(2030, 1, 1),
        active=True,
    )
    membership = await school_membership_factory(user=user, school=school, is_primary=True)
    await db_session.refresh(membership, attribute_names=["roles", "groups"])
    membership.roles.append(role)
    membership.groups.append(group)
    await db_session.refresh(user, attribute_names=["legal_wards", "legal_guardians"])
    user.legal_wards.append(ward)
    user.legal_guardians.append(guardian)
    await db_session.flush()
    db_session.expunge_all()

    return (
        SQLAlchemyUserManager(db_session),
        user.public_id,
        SearchQuery(where=Filter(field="name", op=Operator.EQ, value="projection-user")),
        {
            "name": "projection-user",
            "record_uid": "user-record-uid",
            "source_uid": "user-source-uid",
            "firstname": "Projection",
            "lastname": "User",
            "email": "projection-user@example.org",
            "birthday": date(2010, 1, 1),
            "expiration_date": date(2030, 1, 1),
            "active": True,
            "school_name": "projection-user-school",
            "group_name": "projection-user-group",
            "role_name": "projection-user-role",
            "ward_name": "projection-ward",
            "guardian_name": "projection-guardian",
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", METHODS)
@pytest.mark.parametrize("load_attr", SCHOOL_LOAD_ATTRS)
async def test_school_manager_load_spec_projection_matrix(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    load_attr: str,
    method_name: Literal["get", "search"],
) -> None:
    manager, public_id, query, context = await _setup_school_case(db_session, school_factory)
    spec = LoadSpec.from_attributes(load_attr)
    result = await _fetch_loaded_record(manager, public_id, query, spec, method_name)

    _assert_only_expected_fields_loaded(result, {load_attr})
    assert getattr(result, load_attr) == context[load_attr]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", METHODS)
@pytest.mark.parametrize("load_attr", ROLE_LOAD_ATTRS)
async def test_role_manager_load_spec_projection_matrix(
    db_session: AsyncSession,
    role_factory: RoleFactory,
    load_attr: str,
    method_name: Literal["get", "search"],
) -> None:
    manager, public_id, query, context = await _setup_role_case(db_session, role_factory)
    spec = LoadSpec.from_attributes(load_attr)
    result = await _fetch_loaded_record(manager, public_id, query, spec, method_name)

    _assert_only_expected_fields_loaded(result, {load_attr})
    assert getattr(result, load_attr) == context[load_attr]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", METHODS)
@pytest.mark.parametrize("load_attr", GROUP_LOAD_ATTRS)
async def test_group_manager_load_spec_projection_matrix(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
    role_factory: RoleFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
    load_attr: str,
    method_name: Literal["get", "search"],
) -> None:
    manager, public_id, query, context = await _setup_group_case(
        db_session,
        school_factory,
        group_factory,
        roles_factory,
        user_factory,
        role_factory,
        school_membership_factory,
    )
    spec = LoadSpec.from_attributes(load_attr)
    result = await _fetch_loaded_record(manager, public_id, query, spec, method_name)

    _assert_only_expected_fields_loaded(result, {load_attr, "school"})
    if load_attr in {"record_uid", "source_uid", "name", "display_name", "create_share", "email"}:
        assert getattr(result, load_attr) == context[load_attr]
    elif load_attr == "roles":
        assert not isinstance(result.roles, UnloadedType)
        assert {r.name for r in result.roles} == context["roles"]
    elif load_attr == "allowed_email_senders_users":
        assert not isinstance(result.allowed_email_senders_users, UnloadedType)
        assert {sender_user.name for sender_user in result.allowed_email_senders_users} == {
            context["sender_user"]
        }
    elif load_attr == "allowed_email_senders_groups":
        assert not isinstance(result.allowed_email_senders_groups, UnloadedType)
        assert {sender_group.name for sender_group in result.allowed_email_senders_groups} == {
            context["sender_group"]
        }
    elif load_attr == "members":
        assert not isinstance(result.members, UnloadedType)
        assert {member.name for member in result.members} == {context["member_user"]}
    elif load_attr == "member_roles":
        assert not isinstance(result.member_roles, UnloadedType)
        assert {member_role.name for member_role in result.member_roles} == {context["member_role"]}
    elif load_attr == "school":
        assert not isinstance(result.school, UnloadedType)
        assert result.school.name == context["school_name"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", METHODS)
@pytest.mark.parametrize("load_attr", USER_LOAD_ATTRS)
async def test_user_manager_load_spec_projection_matrix(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
    role_factory: RoleFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
    load_attr: str,
    method_name: Literal["get", "search"],
) -> None:
    manager, public_id, query, context = await _setup_user_case(
        db_session,
        school_factory,
        group_factory,
        roles_factory,
        role_factory,
        user_factory,
        school_membership_factory,
    )
    spec = LoadSpec.from_attributes(load_attr)
    result = await _fetch_loaded_record(manager, public_id, query, spec, method_name)

    _assert_only_expected_fields_loaded(result, _expected_user_loaded_fields(load_attr))
    if load_attr in {
        "record_uid",
        "source_uid",
        "name",
        "firstname",
        "lastname",
        "email",
        "birthday",
        "expiration_date",
        "active",
    }:
        assert getattr(result, load_attr) == context[load_attr]
        return

    if load_attr in USER_MEMBERSHIP_TRIGGERS:
        assert not isinstance(result.school_memberships, UnloadedType)
        membership = next(iter(result.school_memberships.values()))
        assert membership.school.name == context["school_name"]
    if load_attr == "primary_school":
        assert not isinstance(result.primary_school, UnloadedType)
        assert result.primary_school.name == context["school_name"]
    if load_attr == "groups":
        assert not isinstance(result.groups, UnloadedType)
        assert {user_group.name for user_group in result.groups} == {context["group_name"]}
    if load_attr == "roles":
        assert not isinstance(result.roles, UnloadedType)
        assert {user_role.name for user_role in result.roles} == {context["role_name"]}
    if load_attr == "legal_wards":
        assert not isinstance(result.legal_wards, UnloadedType)
        assert {related.name for related in result.legal_wards} == {context["ward_name"]}
    if load_attr == "legal_guardians":
        assert not isinstance(result.legal_guardians, UnloadedType)
        assert {related.name for related in result.legal_guardians} == {context["guardian_name"]}
