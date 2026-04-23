from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.test_types import (
    AsyncGroupFactory,
    AsyncGroupTypeFactory,
    AsyncRoleFactory,
    AsyncSchoolFactory,
    AsyncUserFactory,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupManager,
    SQLAlchemyRoleManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.domain import Group, NotFound, Role, School, SchoolMembership, User
from ucsschool_objects.core.domain.models import UNLOADED, UNSET
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)

# ---------------------------------------------------------------------------
# Domain builders: concrete defaults, references by public_id only
# ---------------------------------------------------------------------------


def _build_school_reference(public_id: UUID, *, name: str = "school-ref") -> School:
    return School(
        public_id=public_id,
        record_uid=f"rec-{name}",
        source_uid=f"src-{name}",
        name=name,
        display_name={"en": name},
        educational_servers=set({"edu.example.com"}),
        administrative_servers=set({"adm.example.com"}),
    )


def _build_role_reference(public_id: UUID, *, name: str = "role-ref") -> Role:
    return Role(public_id=public_id, name=name, display_name={"en": name})


def _build_group_reference(public_id: UUID, *, name: str = "group-ref") -> Group:
    return Group(
        public_id=public_id,
        record_uid=f"rec-{name}",
        source_uid=f"src-{name}",
        name=name,
        display_name={"en": name},
        create_share=False,
        group_type="workgroup",
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        member_roles=set(),
        school=_build_school_reference(uuid.uuid4(), name=f"{name}-school"),
        email=None,
    )


def _build_user_reference(public_id: UUID, *, name: str = "user-ref") -> User:
    return User(
        public_id=public_id,
        record_uid=f"rec-{name}",
        source_uid=f"src-{name}",
        name=name,
        firstname="Ref",
        lastname="User",
        active=True,
        school_memberships={},
        legal_wards=set(),
        legal_guardians=set(),
    )


# ---------------------------------------------------------------------------
# School manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "school_data,expected",
    [
        pytest.param(
            {
                "public_id": uuid.uuid4(),
                "record_uid": "rec-s1",
                "source_uid": "src-s1",
                "name": "school-explicit-id",
                "display_name": {"en": "School Explicit"},
                "educational_servers": set({"edu-1.example.com"}),
                "administrative_servers": set({"adm-1.example.com"}),
                "class_share_file_server": "classfs.example.com",
                "home_share_file_server": "homefs.example.com",
            },
            {"name": "school-explicit-id", "class_share_file_server": "classfs.example.com"},
            id="explicit-public-id",
        ),
        pytest.param(
            {
                "record_uid": "rec-s2",
                "source_uid": "src-s2",
                "name": "school-auto-id",
                "display_name": {"en": "School Auto"},
                "educational_servers": set({"edu-2.example.com"}),
                "administrative_servers": set({"adm-2.example.com"}),
            },
            {"name": "school-auto-id", "class_share_file_server": None},
            id="auto-public-id-default-optionals",
        ),
        pytest.param(
            {
                "public_id": uuid.uuid4(),
                "record_uid": "rec-s3",
                "source_uid": "src-s3",
                "name": "school-multi-servers",
                "display_name": {"en": "School Multi"},
                "educational_servers": set({"edu-a.example.com", "edu-b.example.com"}),
                "administrative_servers": set({"adm-a.example.com"}),
                "class_share_file_server": None,
                "home_share_file_server": None,
            },
            {"name": "school-multi-servers"},
            id="multi-server-values",
        ),
    ],
)
async def test_school_manager_create_success(
    db_session: AsyncSession,
    school_data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    school = School(**school_data)
    await SQLAlchemySchoolManager(db_session).create(school)

    persisted = (
        await db_session.execute(select(SchoolModel).where(SchoolModel.name == school_data["name"]))
    ).scalar_one()
    for attr, expected_value in expected.items():
        assert getattr(persisted, attr) == expected_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "school_data,expected_exception",
    [
        pytest.param(
            {
                "record_uid": "rec-s-fail-empty-edu",
                "source_uid": "src-s-fail-empty-edu",
                "name": "school-fail-empty-edu",
                "display_name": {"en": "Fail"},
                "educational_servers": set(),
                "administrative_servers": set({"adm.example.com"}),
            },
            ValueError,
            id="empty-educational-servers",
        ),
        pytest.param(
            {
                "record_uid": UNLOADED,
                "source_uid": "src-s-fail-null-record",
                "name": "school-fail-null-record",
                "display_name": {"en": "Fail"},
                "educational_servers": set({"edu.example.com"}),
                "administrative_servers": set({"adm.example.com"}),
            },
            ValueError,
            id="UNLOADED-record-uid",
        ),
        pytest.param(
            {
                "record_uid": None,
                "source_uid": "src-s-fail-null-record",
                "name": "school-fail-null-record",
                "display_name": {"en": "Fail"},
                "educational_servers": set({"edu.example.com"}),
                "administrative_servers": set({"adm.example.com"}),
            },
            IntegrityError,
            id="null-record-uid",
        ),
    ],
)
async def test_school_manager_create_failure(
    db_session: AsyncSession,
    school_data: dict[str, Any],
    expected_exception: type[Exception],
) -> None:
    with pytest.raises(expected_exception):
        await SQLAlchemySchoolManager(db_session).create(School(**school_data))


# ---------------------------------------------------------------------------
# Role manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_data",
    [
        pytest.param(
            {
                "public_id": uuid.uuid4(),
                "name": "school:teacher",
                "display_name": {"en": "Teacher"},
            },
            id="explicit-public-id",
        ),
        pytest.param(
            {
                "public_id": uuid.uuid4(),
                "name": "school:student",
                "display_name": {"en": "Student", "de": "Schueler"},
            },
            id="multi-locale-display-name",
        ),
        pytest.param(
            {
                "name": "school:admin",
                "display_name": {"en": "Admin"},
            },
            id="auto-public-id",
        ),
    ],
)
async def test_role_manager_create_success(
    db_session: AsyncSession,
    role_data: dict[str, Any],
) -> None:
    role = Role(**role_data)
    await SQLAlchemyRoleManager(db_session).create(role)

    persisted = (
        await db_session.execute(select(RoleModel).where(RoleModel.name == role_data["name"]))
    ).scalar_one()
    assert persisted.name == role_data["name"]
    assert persisted.display_name == role_data["display_name"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_existing,role_data,expected_exception",
    [
        pytest.param(
            True,
            {"name": "school:dup", "display_name": {"en": "Duplicate"}},
            IntegrityError,
            id="duplicate-role-name",
        ),
        pytest.param(
            False,
            {"name": None, "display_name": {"en": "Null Name"}},
            IntegrityError,
            id="null-role-name",
        ),
    ],
)
async def test_role_manager_create_failure(
    db_session: AsyncSession,
    setup_existing: bool,
    role_data: dict[str, Any],
    expected_exception: type[Exception],
) -> None:
    manager = SQLAlchemyRoleManager(db_session)
    if setup_existing:
        await manager.create(Role(name="school:dup", display_name={"en": "Existing"}))

    with pytest.raises(expected_exception):
        await manager.create(Role(**role_data))


# ---------------------------------------------------------------------------
# Group manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupCreateExpectation:
    group: Group
    expected_role_names: set[str]
    expected_sender_user_names: set[str]
    expected_sender_group_names: set[str]


@dataclass(frozen=True)
class GroupCreateFailureExpectation:
    group: Group
    expected_exception: type[Exception]


GroupCreateSetup = Callable[
    [AsyncSchoolFactory, AsyncGroupTypeFactory, AsyncRoleFactory, AsyncUserFactory, AsyncGroupFactory],
    Awaitable[GroupCreateExpectation],
]
GroupCreateFailSetup = Callable[
    [
        AsyncSchoolFactory,
        AsyncGroupTypeFactory,
        AsyncRoleFactory,
        AsyncUserFactory,
        AsyncGroupFactory,
    ],
    Awaitable[GroupCreateFailureExpectation],
]


async def _setup_group_create_full(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateExpectation:
    school_model = await school_factory(name="group-school-full")
    group_type_model = await group_type_factory(name="group-type-full")
    role_model = await role_factory(name="group-role-full")
    sender_user = await user_factory(name="sender-user-full")
    sender_group = await group_factory(name="sender-group-full")

    group = Group(
        public_id=uuid.uuid4(),
        record_uid="rec-group-full",
        source_uid="src-group-full",
        name="group-create-full",
        display_name={"en": "Group Full"},
        create_share=True,
        group_type=group_type_model.name,
        allowed_email_senders_users=set(
            {_build_user_reference(sender_user.public_id, name=sender_user.name)}
        ),
        allowed_email_senders_groups=set(
            {_build_group_reference(sender_group.public_id, name=sender_group.name)}
        ),
        member_roles=set({_build_role_reference(role_model.public_id, name=role_model.name)}),
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        email="group-full@example.com",
    )
    return GroupCreateExpectation(
        group=group,
        expected_role_names={role_model.name},
        expected_sender_user_names={sender_user.name},
        expected_sender_group_names={sender_group.name},
    )


async def _setup_group_create_minimal(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateExpectation:
    school_model = await school_factory(name="group-school-min")
    group_type_model = await group_type_factory(name="group-type-min")

    group = Group(
        public_id=UNSET,
        record_uid="rec-group-min",
        source_uid="src-group-min",
        name="group-create-min",
        display_name={"en": "Group Min"},
        create_share=False,
        group_type=group_type_model.name,
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        member_roles=set(),
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        email=None,
    )
    return GroupCreateExpectation(
        group=group,
        expected_role_names=set(),
        expected_sender_user_names=set(),
        expected_sender_group_names=set(),
    )


async def _setup_group_create_missing_group_type(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    school_model = await school_factory(name="group-school-fail-type")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-type",
            source_uid="src-group-fail-type",
            name="group-fail-type",
            display_name={"en": "Group Fail Type"},
            create_share=False,
            group_type="missing-group-type",
            allowed_email_senders_users=set(),
            allowed_email_senders_groups=set(),
            member_roles=set(),
            school=_build_school_reference(school_model.public_id, name=school_model.name),
            email=None,
        ),
        expected_exception=NotFound,
    )


async def _setup_group_create_missing_school(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    group_type_model = await group_type_factory(name="group-type-fail-school")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-school",
            source_uid="src-group-fail-school",
            name="group-fail-school",
            display_name={"en": "Group Fail School"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set(),
            allowed_email_senders_groups=set(),
            member_roles=set(),
            school=_build_school_reference(uuid.uuid4(), name="ghost-school"),
            email=None,
        ),
        expected_exception=NotFound,
    )


async def _setup_group_create_missing_role(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    school_model = await school_factory(name="group-school-fail-role")
    group_type_model = await group_type_factory(name="group-type-fail-role")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-role",
            source_uid="src-group-fail-role",
            name="group-fail-role",
            display_name={"en": "Group Fail Role"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set(),
            allowed_email_senders_groups=set(),
            member_roles=set({_build_role_reference(uuid.uuid4(), name="ghost-role")}),
            school=_build_school_reference(school_model.public_id, name=school_model.name),
            email=None,
        ),
        expected_exception=NotFound,
    )


async def _setup_group_create_missing_sender_user(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    school_model = await school_factory(name="group-school-fail-sender-user")
    group_type_model = await group_type_factory(name="group-type-fail-sender-user")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-sender-user",
            source_uid="src-group-fail-sender-user",
            name="group-fail-sender-user",
            display_name={"en": "Group Fail Sender User"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set({_build_user_reference(uuid.uuid4(), name="ghost-user")}),
            allowed_email_senders_groups=set(),
            member_roles=set(),
            school=_build_school_reference(school_model.public_id, name=school_model.name),
            email=None,
        ),
        expected_exception=NotFound,
    )


async def _setup_group_create_missing_sender_group(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    school_model = await school_factory(name="group-school-fail-sender-group")
    group_type_model = await group_type_factory(name="group-type-fail-sender-group")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-sender-group",
            source_uid="src-group-fail-sender-group",
            name="group-fail-sender-group",
            display_name={"en": "Group Fail Sender Group"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set(),
            allowed_email_senders_groups=set(
                {_build_group_reference(uuid.uuid4(), name="ghost-sender-group")}
            ),
            member_roles=set(),
            school=_build_school_reference(school_model.public_id, name=school_model.name),
            email=None,
        ),
        expected_exception=NotFound,
    )


async def _setup_group_create_sender_user_without_public_id(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    school_model = await school_factory(name="group-school-fail-sender-user-public-id")
    group_type_model = await group_type_factory(name="group-type-fail-sender-user-public-id")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-sender-user-public-id",
            source_uid="src-group-fail-sender-user-public-id",
            name="group-fail-sender-user-public-id",
            display_name={"en": "Group Fail Sender User Public Id"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set(
                {
                    User(
                        record_uid="rec-invalid-sender-user",
                        source_uid="src-invalid-sender-user",
                        name="invalid-sender-user",
                        firstname="Invalid",
                        lastname="Sender",
                        active=True,
                        school_memberships={},
                        legal_wards=set(),
                        legal_guardians=set(),
                    )
                }
            ),
            allowed_email_senders_groups=set(),
            member_roles=set(),
            school=_build_school_reference(school_model.public_id, name=school_model.name),
            email=None,
        ),
        expected_exception=ValueError,
    )


async def _setup_group_create_sender_group_without_public_id(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    school_model = await school_factory(name="group-school-fail-sender-group-public-id")
    group_type_model = await group_type_factory(name="group-type-fail-sender-group-public-id")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-sender-group-public-id",
            source_uid="src-group-fail-sender-group-public-id",
            name="group-fail-sender-group-public-id",
            display_name={"en": "Group Fail Sender Group Public Id"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set(),
            allowed_email_senders_groups=set(
                {
                    Group(
                        record_uid="rec-invalid-sender-group",
                        source_uid="src-invalid-sender-group",
                        name="invalid-sender-group",
                        display_name={"en": "Invalid Sender Group"},
                        create_share=False,
                        group_type="workgroup",
                        allowed_email_senders_users=set(),
                        allowed_email_senders_groups=set(),
                        member_roles=set(),
                        school=_build_school_reference(
                            school_model.public_id,
                            name=school_model.name,
                        ),
                        email=None,
                    )
                }
            ),
            member_roles=set(),
            school=_build_school_reference(school_model.public_id, name=school_model.name),
            email=None,
        ),
        expected_exception=ValueError,
    )


async def _setup_group_create_school_without_public_id(
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
) -> GroupCreateFailureExpectation:
    group_type_model = await group_type_factory(name="group-type-fail-school-public-id")
    return GroupCreateFailureExpectation(
        group=Group(
            public_id=uuid.uuid4(),
            record_uid="rec-group-fail-school-public-id",
            source_uid="src-group-fail-school-public-id",
            name="group-fail-school-public-id",
            display_name={"en": "Group Fail School Public Id"},
            create_share=False,
            group_type=group_type_model.name,
            allowed_email_senders_users=set(),
            allowed_email_senders_groups=set(),
            member_roles=set(),
            school=School(
                record_uid="rec-invalid-school",
                source_uid="src-invalid-school",
                name="invalid-school",
                display_name={"en": "Invalid School"},
                educational_servers=set({"edu.example.com"}),
                administrative_servers=set({"adm.example.com"}),
            ),
            email=None,
        ),
        expected_exception=ValueError,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_group_create_full, id="full"),
        pytest.param(_setup_group_create_minimal, id="minimal-empty-relations"),
    ],
)
async def test_group_manager_create_success(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
    setup_case: GroupCreateSetup,
) -> None:
    expectation = await setup_case(
        school_factory,
        group_type_factory,
        role_factory,
        user_factory,
        group_factory,
    )

    await SQLAlchemyGroupManager(db_session).create(expectation.group)

    persisted = (
        await db_session.execute(
            select(GroupModel)
            .options(
                selectinload(GroupModel.member_roles),
                selectinload(GroupModel.allowed_email_senders_users),
                selectinload(GroupModel.allowed_email_senders_groups),
            )
            .where(GroupModel.name == expectation.group.name)
        )
    ).scalar_one()
    assert {role.name for role in persisted.member_roles} == expectation.expected_role_names
    assert {
        user.name for user in persisted.allowed_email_senders_users
    } == expectation.expected_sender_user_names
    assert {
        group.name for group in persisted.allowed_email_senders_groups
    } == expectation.expected_sender_group_names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_group_create_missing_group_type, id="missing-group-type"),
        pytest.param(_setup_group_create_missing_school, id="missing-school"),
        pytest.param(_setup_group_create_missing_role, id="missing-role"),
        pytest.param(_setup_group_create_missing_sender_user, id="missing-sender-user"),
        pytest.param(_setup_group_create_missing_sender_group, id="missing-sender-group"),
        pytest.param(
            _setup_group_create_sender_user_without_public_id,
            id="sender-user-without-public-id",
        ),
        pytest.param(
            _setup_group_create_sender_group_without_public_id,
            id="sender-group-without-public-id",
        ),
        pytest.param(_setup_group_create_school_without_public_id, id="school-without-public-id"),
    ],
)
async def test_group_manager_create_failure(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
    group_type_factory: AsyncGroupTypeFactory,
    role_factory: AsyncRoleFactory,
    user_factory: AsyncUserFactory,
    group_factory: AsyncGroupFactory,
    setup_case: GroupCreateFailSetup,
) -> None:
    expectation = await setup_case(
        school_factory,
        group_type_factory,
        role_factory,
        user_factory,
        group_factory,
    )

    with pytest.raises(expectation.expected_exception):
        await SQLAlchemyGroupManager(db_session).create(expectation.group)


# ---------------------------------------------------------------------------
# User manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserCreateExpectation:
    user: User
    expected_school_names: set[str]
    expected_role_names: set[str]
    expected_ward_names: set[str]
    expected_guardian_names: set[str]


@dataclass(frozen=True)
class UserCreateFailureExpectation:
    user: User
    expected_exception: type[Exception]


UserCreateSetup = Callable[
    [AsyncSchoolFactory, AsyncRoleFactory, AsyncGroupFactory, AsyncUserFactory],
    Awaitable[UserCreateExpectation],
]
UserCreateFailSetup = Callable[
    [AsyncSchoolFactory, AsyncRoleFactory, AsyncGroupFactory],
    Awaitable[UserCreateFailureExpectation],
]


async def _setup_user_create_full(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
) -> UserCreateExpectation:
    school_model = await school_factory(name="user-school-full")
    role_model = await role_factory(name="user-role-full")
    group_model = await group_factory(name="user-group-full")
    ward_model = await user_factory(name="user-ward-full")
    guardian_model = await user_factory(name="user-guardian-full")

    membership = SchoolMembership(
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        is_primary=True,
        roles=set({_build_role_reference(role_model.public_id, name=role_model.name)}),
        groups=set({_build_group_reference(group_model.public_id, name=group_model.name)}),
    )
    user = User(
        public_id=uuid.uuid4(),
        record_uid="rec-user-full",
        source_uid="src-user-full",
        name="user-create-full",
        firstname="Create",
        lastname="Full",
        active=True,
        school_memberships={school_model.public_id: membership},
        legal_wards=set({_build_user_reference(ward_model.public_id, name=ward_model.name)}),
        legal_guardians=set({_build_user_reference(guardian_model.public_id, name=guardian_model.name)}),
        email="user-full@example.com",
    )
    return UserCreateExpectation(
        user=user,
        expected_school_names={school_model.name},
        expected_role_names={role_model.name},
        expected_ward_names={ward_model.name},
        expected_guardian_names={guardian_model.name},
    )


async def _setup_user_create_minimal(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
) -> UserCreateExpectation:
    user = User(
        public_id=uuid.uuid4(),
        record_uid="rec-user-min",
        source_uid="src-user-min",
        name="user-create-min",
        firstname="Create",
        lastname="Min",
        active=True,
        school_memberships={},
        legal_wards=set(),
        legal_guardians=set(),
    )
    return UserCreateExpectation(
        user=user,
        expected_school_names=set(),
        expected_role_names=set(),
        expected_ward_names=set(),
        expected_guardian_names=set(),
    )


async def _setup_user_create_multi_membership(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
) -> UserCreateExpectation:
    school_a = await school_factory(name="user-school-a")
    school_b = await school_factory(name="user-school-b")
    role_model = await role_factory(name="user-role-multi")
    group_model = await group_factory(name="user-group-multi")

    def membership(school_id: UUID, school_name: str, is_primary: bool) -> SchoolMembership:
        return SchoolMembership(
            school=_build_school_reference(school_id, name=school_name),
            is_primary=is_primary,
            roles=set({_build_role_reference(role_model.public_id, name=role_model.name)}),
            groups=set({_build_group_reference(group_model.public_id, name=group_model.name)}),
        )

    membership_a = membership(school_a.public_id, school_a.name, True)
    membership_b = membership(school_b.public_id, school_b.name, False)

    user = User(
        public_id=uuid.uuid4(),
        record_uid="rec-user-multi",
        source_uid="src-user-multi",
        name="user-create-multi",
        firstname="Create",
        lastname="Multi",
        active=True,
        school_memberships={
            school_a.public_id: membership_a,
            school_b.public_id: membership_b,
        },
        legal_wards=set(),
        legal_guardians=set(),
    )
    return UserCreateExpectation(
        user=user,
        expected_school_names={school_a.name, school_b.name},
        expected_role_names={role_model.name},
        expected_ward_names=set(),
        expected_guardian_names=set(),
    )


async def _setup_user_create_unloaded_relations(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
) -> UserCreateExpectation:
    user = User(
        record_uid="rec-user-unloaded",
        source_uid="src-user-unloaded",
        name="user-create-unloaded",
        firstname="Create",
        lastname="Unloaded",
        active=True,
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )
    return UserCreateExpectation(
        user=user,
        expected_school_names=set(),
        expected_role_names=set(),
        expected_ward_names=set(),
        expected_guardian_names=set(),
    )


async def _setup_user_create_missing_school(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    role_model = await role_factory(name="user-role-fail-school")
    group_model = await group_factory(name="user-group-fail-school")
    ghost_school_id = uuid.uuid4()
    membership = SchoolMembership(
        school=_build_school_reference(ghost_school_id, name="ghost-school"),
        is_primary=True,
        roles=set({_build_role_reference(role_model.public_id, name=role_model.name)}),
        groups=set({_build_group_reference(group_model.public_id, name=group_model.name)}),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-school",
            source_uid="src-user-fail-school",
            name="user-fail-school",
            firstname="Fail",
            lastname="School",
            active=True,
            school_memberships={ghost_school_id: membership},
            legal_wards=set(),
            legal_guardians=set(),
        ),
        expected_exception=NotFound,
    )


async def _setup_user_create_missing_role(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    school_model = await school_factory(name="user-school-fail-role")
    group_model = await group_factory(name="user-group-fail-role")
    membership = SchoolMembership(
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        is_primary=True,
        roles=set({_build_role_reference(uuid.uuid4(), name="ghost-role")}),
        groups=set({_build_group_reference(group_model.public_id, name=group_model.name)}),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-role",
            source_uid="src-user-fail-role",
            name="user-fail-role",
            firstname="Fail",
            lastname="Role",
            active=True,
            school_memberships={school_model.public_id: membership},
            legal_wards=set(),
            legal_guardians=set(),
        ),
        expected_exception=NotFound,
    )


async def _setup_user_create_missing_ward(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    school_model = await school_factory(name="user-school-fail-ward")
    membership = SchoolMembership(
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        is_primary=True,
        roles=set(),
        groups=set(),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-ward",
            source_uid="src-user-fail-ward",
            name="user-fail-ward",
            firstname="Fail",
            lastname="Ward",
            active=True,
            school_memberships={school_model.public_id: membership},
            legal_wards=set({_build_user_reference(uuid.uuid4(), name="ghost-ward")}),
            legal_guardians=set(),
        ),
        expected_exception=NotFound,
    )


async def _setup_user_create_membership_school_without_public_id(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    membership = SchoolMembership(
        school=School(
            record_uid="rec-invalid-school",
            source_uid="src-invalid-school",
            name="invalid-school",
            display_name={"en": "Invalid School"},
            educational_servers=set({"edu.example.com"}),
            administrative_servers=set({"adm.example.com"}),
        ),
        is_primary=True,
        roles=set(),
        groups=set(),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-membership-school-public-id",
            source_uid="src-user-fail-membership-school-public-id",
            name="user-fail-membership-school-public-id",
            firstname="Fail",
            lastname="MembershipSchoolPublicId",
            active=True,
            school_memberships={uuid.uuid4(): membership},
            legal_wards=set(),
            legal_guardians=set(),
        ),
        expected_exception=ValueError,
    )


async def _setup_user_create_membership_key_mismatch(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    school_model = await school_factory(name="user-school-fail-membership-key")
    membership = SchoolMembership(
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        is_primary=True,
        roles=set(),
        groups=set(),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-membership-key",
            source_uid="src-user-fail-membership-key",
            name="user-fail-membership-key",
            firstname="Fail",
            lastname="MembershipKey",
            active=True,
            school_memberships={uuid.uuid4(): membership},
            legal_wards=set(),
            legal_guardians=set(),
        ),
        expected_exception=ValueError,
    )


async def _setup_user_create_membership_role_without_public_id(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    school_model = await school_factory(name="user-school-fail-membership-role-public-id")
    membership = SchoolMembership(
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        is_primary=True,
        roles=set({Role(name="role-without-public-id", display_name={"en": "Role Without Public Id"})}),
        groups=set(),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-membership-role-public-id",
            source_uid="src-user-fail-membership-role-public-id",
            name="user-fail-membership-role-public-id",
            firstname="Fail",
            lastname="MembershipRolePublicId",
            active=True,
            school_memberships={school_model.public_id: membership},
            legal_wards=set(),
            legal_guardians=set(),
        ),
        expected_exception=ValueError,
    )


async def _setup_user_create_membership_group_without_public_id(
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
) -> UserCreateFailureExpectation:
    school_model = await school_factory(name="user-school-fail-membership-group-public-id")
    membership = SchoolMembership(
        school=_build_school_reference(school_model.public_id, name=school_model.name),
        is_primary=True,
        roles=set(),
        groups=set(
            {
                Group(
                    record_uid="rec-group-without-public-id",
                    source_uid="src-group-without-public-id",
                    name="group-without-public-id",
                    display_name={"en": "Group Without Public Id"},
                    create_share=False,
                    group_type="workgroup",
                    allowed_email_senders_users=set(),
                    allowed_email_senders_groups=set(),
                    member_roles=set(),
                    school=_build_school_reference(school_model.public_id, name=school_model.name),
                    email=None,
                )
            }
        ),
    )
    return UserCreateFailureExpectation(
        user=User(
            public_id=uuid.uuid4(),
            record_uid="rec-user-fail-membership-group-public-id",
            source_uid="src-user-fail-membership-group-public-id",
            name="user-fail-membership-group-public-id",
            firstname="Fail",
            lastname="MembershipGroupPublicId",
            active=True,
            school_memberships={school_model.public_id: membership},
            legal_wards=set(),
            legal_guardians=set(),
        ),
        expected_exception=ValueError,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_user_create_full, id="full"),
        pytest.param(_setup_user_create_minimal, id="minimal-empty-relations"),
        pytest.param(_setup_user_create_multi_membership, id="multiple-memberships"),
        pytest.param(_setup_user_create_unloaded_relations, id="unloaded-relations-auto-public-id"),
    ],
)
async def test_user_manager_create_success(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
    setup_case: UserCreateSetup,
) -> None:
    expectation = await setup_case(school_factory, role_factory, group_factory, user_factory)

    await SQLAlchemyUserManager(db_session).create(expectation.user)

    persisted = (
        await db_session.execute(
            select(UserModel)
            .options(
                selectinload(UserModel.school_memberships).selectinload(SchoolMembershipModel.school),
                selectinload(UserModel.school_memberships).selectinload(SchoolMembershipModel.roles),
                selectinload(UserModel.legal_wards),
                selectinload(UserModel.legal_guardians),
            )
            .where(UserModel.name == expectation.user.name)
        )
    ).scalar_one()
    assert {m.school.name for m in persisted.school_memberships} == expectation.expected_school_names
    assert {
        r.name for m in persisted.school_memberships for r in m.roles
    } == expectation.expected_role_names
    assert {w.name for w in persisted.legal_wards} == expectation.expected_ward_names
    assert {g.name for g in persisted.legal_guardians} == expectation.expected_guardian_names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup_case",
    [
        pytest.param(_setup_user_create_missing_school, id="missing-school"),
        pytest.param(_setup_user_create_missing_role, id="missing-role"),
        pytest.param(_setup_user_create_missing_ward, id="missing-ward"),
        pytest.param(
            _setup_user_create_membership_school_without_public_id,
            id="membership-school-without-public-id",
        ),
        pytest.param(_setup_user_create_membership_key_mismatch, id="membership-key-mismatch"),
        pytest.param(
            _setup_user_create_membership_role_without_public_id,
            id="membership-role-without-public-id",
        ),
        pytest.param(
            _setup_user_create_membership_group_without_public_id,
            id="membership-group-without-public-id",
        ),
    ],
)
async def test_user_manager_create_failure(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    group_factory: AsyncGroupFactory,
    setup_case: UserCreateFailSetup,
) -> None:
    expectation = await setup_case(school_factory, role_factory, group_factory)

    with pytest.raises(expectation.expected_exception):
        await SQLAlchemyUserManager(db_session).create(expectation.user)
