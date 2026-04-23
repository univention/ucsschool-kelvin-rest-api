from __future__ import annotations

import copy
import uuid
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select
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
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers.school_manager import _apply_school_patch
from ucsschool_objects.core.adapters.sqlalchemy.managers.user_manager import _apply_user_patch
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import (
    to_group,
    to_role,
    to_school,
    to_user,
)
from ucsschool_objects.core.domain import NotFound, UnsupportedOperation
from ucsschool_objects.core.domain.patch import _create_patch
from ucsschool_objects.database_models import (
    Group as GroupModel,
    School as SchoolModel,
    User as UserModel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_school(**overrides: object) -> SchoolModel:
    data: dict[str, object] = {
        "record_uid": "rec",
        "source_uid": "src",
        "name": "school",
        "display_name": {"en": "School"},
        "educational_servers": ["edu1"],
        "administrative_servers": ["adm1"],
        "class_share_file_server": None,
        "home_share_file_server": None,
    }
    data.update(overrides)
    return SchoolModel(**data)


def _school_patched(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "record_uid": "rec",
        "source_uid": "src",
        "name": "school",
        "display_name": {"en": "School"},
        "educational_servers": ["edu1"],
        "administrative_servers": ["adm1"],
        "class_share_file_server": None,
        "home_share_file_server": None,
    }
    base.update(overrides)
    return base


def _bare_user(**overrides: object) -> UserModel:
    data: dict[str, object] = {
        "record_uid": "rec",
        "source_uid": "src",
        "name": "user",
        "firstname": "First",
        "lastname": "Last",
        "email": None,
        "active": True,
        "birthday": None,
        "expiration_date": None,
    }
    data.update(overrides)
    return UserModel(**data)


def _user_patched(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "record_uid": "rec",
        "source_uid": "src",
        "name": "user",
        "firstname": "First",
        "lastname": "Last",
        "email": None,
        "active": True,
        "birthday": None,
        "expiration_date": None,
    }
    base.update(overrides)
    return base


async def _load_group_full(session: AsyncSession, public_id: UUID) -> GroupModel:
    result = await session.execute(
        select(GroupModel)
        .where(GroupModel.public_id == public_id)
        .options(
            selectinload(GroupModel.group_type),
            selectinload(GroupModel.school),
            selectinload(GroupModel.member_roles),
            selectinload(GroupModel.allowed_email_senders_users),
            selectinload(GroupModel.allowed_email_senders_groups),
        )
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# apply_school_patch — unit tests (no DB required)
# ---------------------------------------------------------------------------


def test_apply_school_patch_updates_scalar_fields() -> None:
    model = _bare_school()
    _apply_school_patch(model, _school_patched(name="new-name", record_uid="new-rec"))
    assert model.name == "new-name"
    assert model.record_uid == "new-rec"


def test_apply_school_patch_sets_nullable_field() -> None:
    model = _bare_school()
    _apply_school_patch(model, _school_patched(class_share_file_server="srv.example.com"))
    assert model.class_share_file_server == "srv.example.com"


def test_apply_school_patch_clears_nullable_field_to_none() -> None:
    model = _bare_school(class_share_file_server="old.example.com")
    _apply_school_patch(model, _school_patched(class_share_file_server=None))
    assert model.class_share_file_server is None


def test_apply_school_patch_replaces_json_list() -> None:
    model = _bare_school()
    _apply_school_patch(model, _school_patched(educational_servers=["edu1", "edu2"]))
    assert model.educational_servers == ["edu1", "edu2"]


def test_apply_school_patch_updates_display_name_dict() -> None:
    model = _bare_school()
    _apply_school_patch(model, _school_patched(display_name={"en": "New", "de": "Neu"}))
    assert model.display_name == {"en": "New", "de": "Neu"}


# ---------------------------------------------------------------------------
# apply_user_patch — unit tests (no DB required)
# ---------------------------------------------------------------------------


def test_apply_user_patch_updates_scalar_fields() -> None:
    model = _bare_user()
    _apply_user_patch(model, _user_patched(name="newuser", email="new@example.com"))
    assert model.name == "newuser"
    assert model.email == "new@example.com"


def test_apply_user_patch_converts_birthday_string_to_date() -> None:
    model = _bare_user()
    _apply_user_patch(model, _user_patched(birthday="2000-06-15"))
    assert model.birthday == date(2000, 6, 15)


def test_apply_user_patch_converts_expiration_date_string_to_date() -> None:
    model = _bare_user()
    _apply_user_patch(model, _user_patched(expiration_date="2030-12-31"))
    assert model.expiration_date == date(2030, 12, 31)


def test_apply_user_patch_accepts_none_for_date_fields() -> None:
    model = _bare_user(birthday=date(2000, 1, 1), expiration_date=date(2030, 1, 1))
    _apply_user_patch(model, _user_patched(birthday=None, expiration_date=None))
    assert model.birthday is None
    assert model.expiration_date is None


def test_apply_user_patch_toggles_active_flag() -> None:
    model = _bare_user(active=True)
    _apply_user_patch(model, _user_patched(active=False))
    assert model.active is False


# ---------------------------------------------------------------------------
# SQLAlchemySchoolManager.modify — integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_school_manager_modify_name(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
) -> None:
    school = await school_factory(name="original")
    await SQLAlchemySchoolManager(db_session).modify(
        school.public_id,
        [{"op": "replace", "path": "/name", "value": "updated"}],
    )
    result = (
        await db_session.execute(select(SchoolModel).where(SchoolModel.public_id == school.public_id))
    ).scalar_one()
    assert result.name == "updated"


@pytest.mark.asyncio
async def test_school_manager_modify_educational_servers(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
) -> None:
    school = await school_factory(educational_servers=["edu1"])
    domain = to_school(school)
    dst = copy.copy(domain)
    dst.educational_servers = {"edu1", "edu2"}
    ops = _create_patch(domain, dst)

    await SQLAlchemySchoolManager(db_session).modify(school.public_id, ops)

    result = (
        await db_session.execute(select(SchoolModel).where(SchoolModel.public_id == school.public_id))
    ).scalar_one()
    assert set(result.educational_servers) == {"edu1", "edu2"}


@pytest.mark.asyncio
async def test_school_manager_modify_not_found_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFound):
        await SQLAlchemySchoolManager(db_session).modify(
            uuid.uuid4(),
            [{"op": "replace", "path": "/name", "value": "x"}],
        )


# ---------------------------------------------------------------------------
# SQLAlchemyGroupManager.modify — integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_manager_modify_name(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory(name="original-group")
    await SQLAlchemyGroupManager(db_session).modify(
        group.public_id,
        [{"op": "replace", "path": "/name", "value": "updated-group"}],
    )
    result = (
        await db_session.execute(select(GroupModel).where(GroupModel.public_id == group.public_id))
    ).scalar_one()
    assert result.name == "updated-group"


@pytest.mark.asyncio
async def test_group_manager_modify_has_share(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory(has_share=False)
    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.create_share = True
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    result = (
        await db_session.execute(select(GroupModel).where(GroupModel.public_id == group.public_id))
    ).scalar_one()
    assert result.has_share is True


@pytest.mark.asyncio
async def test_group_manager_modify_adds_member_role(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    role_factory: AsyncRoleFactory,
) -> None:
    group = await group_factory()
    role = await role_factory()

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.member_roles = {to_role(role)}
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert any(r.public_id == role.public_id for r in loaded.member_roles)


@pytest.mark.asyncio
async def test_group_manager_modify_group_type(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    group_type_factory: AsyncGroupTypeFactory,
) -> None:
    group = await group_factory()
    new_gt = await group_type_factory(name="new-group-type")

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.group_type = new_gt.name
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert loaded.group_type.name == new_gt.name


@pytest.mark.asyncio
async def test_group_manager_modify_unsupported_path_raises(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyGroupManager(db_session).modify(
            group.public_id,
            [{"op": "replace", "path": "/school/name", "value": "x"}],
        )


@pytest.mark.asyncio
async def test_group_manager_modify_not_found_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFound):
        await SQLAlchemyGroupManager(db_session).modify(
            uuid.uuid4(),
            [{"op": "replace", "path": "/name", "value": "x"}],
        )


# ---------------------------------------------------------------------------
# SQLAlchemyUserManager.modify — integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_manager_modify_name(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory(name="original-user")
    await SQLAlchemyUserManager(db_session).modify(
        user.public_id,
        [{"op": "replace", "path": "/name", "value": "updated-user"}],
    )
    result = (
        await db_session.execute(select(UserModel).where(UserModel.public_id == user.public_id))
    ).scalar_one()
    assert result.name == "updated-user"


@pytest.mark.asyncio
async def test_user_manager_modify_birthday(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory(birthday=date(1990, 1, 1))
    domain = to_user(
        user,
        include_memberships=False,
        include_legal_wards=False,
        include_legal_guardians=False,
    )
    dst = copy.copy(domain)
    dst.birthday = date(2000, 6, 15)
    ops = _create_patch(domain, dst)

    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    result = (
        await db_session.execute(select(UserModel).where(UserModel.public_id == user.public_id))
    ).scalar_one()
    assert result.birthday == date(2000, 6, 15)


@pytest.mark.asyncio
async def test_user_manager_modify_clears_email_to_none(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory(email="before@example.com")
    domain = to_user(
        user,
        include_memberships=False,
        include_legal_wards=False,
        include_legal_guardians=False,
    )
    dst = copy.copy(domain)
    dst.email = None
    ops = _create_patch(domain, dst)

    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    result = (
        await db_session.execute(select(UserModel).where(UserModel.public_id == user.public_id))
    ).scalar_one()
    assert result.email is None


@pytest.mark.asyncio
async def test_user_manager_modify_unsupported_path_raises(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [{"op": "replace", "path": "/school_memberships/some-id/is_primary", "value": True}],
        )


@pytest.mark.asyncio
async def test_user_manager_modify_not_found_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFound):
        await SQLAlchemyUserManager(db_session).modify(
            uuid.uuid4(),
            [{"op": "replace", "path": "/name", "value": "x"}],
        )


# ---------------------------------------------------------------------------
# modify — validation tests (ORM not mutated on invalid patch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_school_manager_modify_invalid_name_raises_and_does_not_persist(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
) -> None:
    school = await school_factory(name="valid-school")
    with pytest.raises(ValueError, match="Invalid school name"):
        await SQLAlchemySchoolManager(db_session).modify(
            school.public_id,
            [{"op": "replace", "path": "/name", "value": "invalid name!"}],
        )
    result = (
        await db_session.execute(select(SchoolModel).where(SchoolModel.public_id == school.public_id))
    ).scalar_one()
    assert result.name == "valid-school"


@pytest.mark.asyncio
async def test_group_manager_modify_empty_name_raises_and_does_not_persist(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory(name="valid-group")
    with pytest.raises(ValueError, match="Group.name"):
        await SQLAlchemyGroupManager(db_session).modify(
            group.public_id,
            [{"op": "replace", "path": "/name", "value": ""}],
        )
    result = (
        await db_session.execute(select(GroupModel).where(GroupModel.public_id == group.public_id))
    ).scalar_one()
    assert result.name == "valid-group"


@pytest.mark.asyncio
async def test_user_manager_modify_empty_name_raises_and_does_not_persist(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory(name="valid-user")
    with pytest.raises(ValueError, match="User.name"):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [{"op": "replace", "path": "/name", "value": ""}],
        )
    result = (
        await db_session.execute(select(UserModel).where(UserModel.public_id == user.public_id))
    ).scalar_one()
    assert result.name == "valid-user"


# ---------------------------------------------------------------------------
# delete — integration tests (school, group, user)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_school_manager_delete_removes_row(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
) -> None:
    school = await school_factory()
    await SQLAlchemySchoolManager(db_session).delete(school.public_id)
    result = (
        await db_session.execute(select(SchoolModel).where(SchoolModel.public_id == school.public_id))
    ).scalar_one_or_none()
    assert result is None


@pytest.mark.asyncio
async def test_school_manager_delete_not_found_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFound):
        await SQLAlchemySchoolManager(db_session).delete(uuid.uuid4())


@pytest.mark.asyncio
async def test_group_manager_delete_removes_row(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory()
    await SQLAlchemyGroupManager(db_session).delete(group.public_id)
    result = (
        await db_session.execute(select(GroupModel).where(GroupModel.public_id == group.public_id))
    ).scalar_one_or_none()
    assert result is None


@pytest.mark.asyncio
async def test_group_manager_delete_not_found_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFound):
        await SQLAlchemyGroupManager(db_session).delete(uuid.uuid4())


@pytest.mark.asyncio
async def test_user_manager_delete_removes_row(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    await SQLAlchemyUserManager(db_session).delete(user.public_id)
    result = (
        await db_session.execute(select(UserModel).where(UserModel.public_id == user.public_id))
    ).scalar_one_or_none()
    assert result is None


@pytest.mark.asyncio
async def test_user_manager_delete_not_found_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotFound):
        await SQLAlchemyUserManager(db_session).delete(uuid.uuid4())
