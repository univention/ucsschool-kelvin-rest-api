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
    AsyncSchoolMembershipFactory,
    AsyncUserFactory,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    _extract_public_ids,
    _sync_scalar_relation,
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
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation
from ucsschool_objects.database_models import (
    Group as GroupModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
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
        "display_name": "School",
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
        "display_name": "School",
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
            selectinload(GroupModel.members).selectinload(SchoolMembershipModel.user),
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


def test_apply_school_patch_updates_display_name() -> None:
    model = _bare_school()
    _apply_school_patch(model, _school_patched(display_name="New"))
    assert model.display_name == "New"


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


def test_extract_public_ids_ignores_items_without_public_id() -> None:
    assert _extract_public_ids([{}]) == set()


@pytest.mark.asyncio
async def test_sync_scalar_relation_clears_optional(db_session: AsyncSession) -> None:
    # We use a dummy object and any model class to test the branch in _shared logic
    class Dummy:
        school = "something"

    model = Dummy()
    await _sync_scalar_relation(
        db_session,
        model,
        "school",
        patched_val=None,
        current_val="something",
        target_model=SchoolModel,
        mandatory=False,
    )
    assert model.school is None


def test_to_user_returns_none_for_null_birthday() -> None:
    model = _bare_user()  # birthday=None by default
    user = to_user(
        model, include_memberships=False, include_legal_wards=False, include_legal_guardians=False
    )
    assert user.birthday is None


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
async def test_group_manager_modify_members(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    school = await school_factory()
    group = await group_factory(school=school)
    user = await user_factory()
    membership = await school_membership_factory(user=user, school=school)

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.members = {
        to_user(
            user, include_memberships=False, include_legal_wards=False, include_legal_guardians=False
        )
    }
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert any(m.id == membership.id for m in loaded.members)


@pytest.mark.asyncio
async def test_group_manager_modify_allowed_email_senders_users(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
) -> None:
    group = await group_factory()
    user = await user_factory()

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.allowed_email_senders_users = {
        to_user(
            user, include_memberships=False, include_legal_wards=False, include_legal_guardians=False
        )
    }
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert any(u.id == user.id for u in loaded.allowed_email_senders_users)


@pytest.mark.asyncio
async def test_group_manager_modify_allowed_email_senders_groups(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory()
    sender_group = await group_factory()

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.allowed_email_senders_groups = {
        to_group(await _load_group_full(db_session, sender_group.public_id))
    }
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert any(g.id == sender_group.id for g in loaded.allowed_email_senders_groups)


@pytest.mark.asyncio
async def test_group_manager_modify_school(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    school_factory: AsyncSchoolFactory,
) -> None:
    school_a = await school_factory()
    school_b = await school_factory()
    group = await group_factory(school=school_a)

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.school = to_school(school_b)
    ops = _create_patch(group_domain, dst, replace_fields=frozenset({"school"}))

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert loaded.school.public_id == school_b.public_id


@pytest.mark.asyncio
async def test_group_manager_modify_members_clear(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    school = await school_factory()
    user = await user_factory()
    membership = await school_membership_factory(user=user, school=school)
    group = await group_factory(school=school, members=[membership])

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.members = set()
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert len(loaded.members) == 0


@pytest.mark.asyncio
async def test_group_manager_modify_allowed_email_senders_users_clear(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    group = await group_factory(allowed_email_senders_users=[user])

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.allowed_email_senders_users = set()
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert len(loaded.allowed_email_senders_users) == 0


@pytest.mark.asyncio
async def test_group_manager_modify_allowed_email_senders_groups_clear(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    sender_group = await group_factory()
    group = await group_factory(allowed_email_senders_groups=[sender_group])

    group_domain = to_group(await _load_group_full(db_session, group.public_id))
    dst = copy.copy(group_domain)
    dst.allowed_email_senders_groups = set()
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert len(loaded.allowed_email_senders_groups) == 0


@pytest.mark.asyncio
async def test_group_manager_modify_school_null_raises(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory()
    # Manually craft a patch that sets school to null, bypassing create_patch logic
    # if necessary, but actually we just want to see if the manager handles it.
    ops: list[JSONPathOperation] = [{"op": "replace", "path": "/school", "value": None}]

    with pytest.raises(ValueError, match="Group.school must not be null"):
        await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)


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
    dst.group_type = {to_role(new_gt)}
    ops = _create_patch(group_domain, dst)

    await SQLAlchemyGroupManager(db_session).modify(group.public_id, ops)

    loaded = await _load_group_full(db_session, group.public_id)
    assert {r.name for r in loaded.group_type} == {new_gt.name}


@pytest.mark.asyncio
async def test_group_manager_modify_group_type_not_found_raises(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory()
    with pytest.raises(NotFound):
        await SQLAlchemyGroupManager(db_session).modify(
            group.public_id, [{"op": "replace", "path": "/group_type", "value": "nonexistent-type"}]
        )


@pytest.mark.asyncio
async def test_group_manager_modify_unsupported_path_raises(
    db_session: AsyncSession,
    group_factory: AsyncGroupFactory,
) -> None:
    group = await group_factory()
    manager = SQLAlchemyGroupManager(db_session)
    # Deep patch on school object
    with pytest.raises(UnsupportedOperation, match="via deep patch"):
        await manager.modify(
            group.public_id,
            [{"op": "replace", "path": "/school/name", "value": "x"}],
        )

    # Deep patch on collection
    with pytest.raises(UnsupportedOperation, match="via deep patch"):
        await manager.modify(
            group.public_id,
            [{"op": "replace", "path": "/members/0/name", "value": "x"}],
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
# SQLAlchemyUserManager.modify — group and legal relation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_manager_modify_groups_in_school_membership(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    group_factory: AsyncGroupFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    user = await user_factory()
    school = await school_factory()
    group_a = await group_factory()
    group_b = await group_factory()
    await school_membership_factory(user=user, school=school, groups=[group_a])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": f"/school_memberships/{school.public_id}/groups",
            "value": [{"public_id": str(group_b.public_id)}],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(SchoolMembershipModel)
            .options(selectinload(SchoolMembershipModel.groups))
            .where(
                SchoolMembershipModel.user_id == user.id,
                SchoolMembershipModel.school_id == school.id,
            )
        )
    ).scalar_one()
    assert {g.public_id for g in updated.groups} == {group_b.public_id}


@pytest.mark.asyncio
async def test_user_manager_modify_roles_in_school_membership(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    role_factory: AsyncRoleFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    user = await user_factory()
    school = await school_factory()
    role_a = await role_factory()
    role_b = await role_factory()
    await school_membership_factory(user=user, school=school, roles=[role_a])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": f"/school_memberships/{school.public_id}/roles",
            "value": [{"public_id": str(role_b.public_id)}],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(SchoolMembershipModel)
            .options(selectinload(SchoolMembershipModel.roles))
            .where(
                SchoolMembershipModel.user_id == user.id,
                SchoolMembershipModel.school_id == school.id,
            )
        )
    ).scalar_one()
    assert {r.public_id for r in updated.roles} == {role_b.public_id}


@pytest.mark.asyncio
async def test_user_manager_modify_school_membership_group_deep_attribute_raises(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [
                {
                    "op": "replace",
                    "path": f"/school_memberships/{uuid.uuid4()}/groups/0/name",
                    "value": "x",
                }
            ],
        )


@pytest.mark.asyncio
async def test_user_manager_modify_school_membership_role_deep_attribute_raises(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [
                {
                    "op": "replace",
                    "path": f"/school_memberships/{uuid.uuid4()}/roles/0/name",
                    "value": "x",
                }
            ],
        )


@pytest.mark.asyncio
async def test_user_manager_modify_school_membership_unsupported_field_path_raises(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [
                {
                    "op": "replace",
                    "path": f"/school_memberships/{uuid.uuid4()}/is_primary",
                    "value": True,
                }
            ],
        )


@pytest.mark.asyncio
async def test_user_manager_modify_legal_guardians(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    guardian_a = await user_factory()
    guardian_b = await user_factory()
    user = await user_factory(legal_guardians=[guardian_a])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": "/legal_guardians",
            "value": [{"public_id": str(guardian_b.public_id)}],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(UserModel)
            .options(selectinload(UserModel.legal_guardians))
            .where(UserModel.public_id == user.public_id)
        )
    ).scalar_one()
    assert {g.public_id for g in updated.legal_guardians} == {guardian_b.public_id}


@pytest.mark.asyncio
async def test_user_manager_modify_legal_guardians_deep_attribute_raises(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [{"op": "replace", "path": "/legal_guardians/0/name", "value": "x"}],
        )


@pytest.mark.asyncio
async def test_user_manager_modify_legal_wards(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    ward_a = await user_factory()
    ward_b = await user_factory()
    user = await user_factory(legal_wards=[ward_a])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": "/legal_wards",
            "value": [{"public_id": str(ward_b.public_id)}],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(UserModel)
            .options(selectinload(UserModel.legal_wards))
            .where(UserModel.public_id == user.public_id)
        )
    ).scalar_one()
    assert {w.public_id for w in updated.legal_wards} == {ward_b.public_id}


@pytest.mark.asyncio
async def test_user_manager_modify_legal_wards_deep_attribute_raises(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    user = await user_factory()
    with pytest.raises(UnsupportedOperation):
        await SQLAlchemyUserManager(db_session).modify(
            user.public_id,
            [{"op": "replace", "path": "/legal_wards/0/name", "value": "x"}],
        )


@pytest.mark.asyncio
async def test_user_manager_modify_groups_unchanged_is_noop(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    group_factory: AsyncGroupFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    user = await user_factory()
    school = await school_factory()
    group_a = await group_factory()
    await school_membership_factory(user=user, school=school, groups=[group_a])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": f"/school_memberships/{school.public_id}/groups",
            "value": [{"public_id": str(group_a.public_id)}],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(SchoolMembershipModel)
            .options(selectinload(SchoolMembershipModel.groups))
            .where(
                SchoolMembershipModel.user_id == user.id,
                SchoolMembershipModel.school_id == school.id,
            )
        )
    ).scalar_one()
    assert {g.public_id for g in updated.groups} == {group_a.public_id}


@pytest.mark.asyncio
async def test_user_manager_modify_groups_clear(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    group_factory: AsyncGroupFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    user = await user_factory()
    school = await school_factory()
    group_a = await group_factory()
    await school_membership_factory(user=user, school=school, groups=[group_a])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": f"/school_memberships/{school.public_id}/groups",
            "value": [],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(SchoolMembershipModel)
            .options(selectinload(SchoolMembershipModel.groups))
            .where(
                SchoolMembershipModel.user_id == user.id,
                SchoolMembershipModel.school_id == school.id,
            )
        )
    ).scalar_one()
    assert updated.groups == []


@pytest.mark.asyncio
async def test_user_manager_modify_legal_guardians_noop(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    guardian = await user_factory()
    user = await user_factory(legal_guardians=[guardian])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": "/legal_guardians",
            "value": [{"public_id": str(guardian.public_id)}],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(UserModel)
            .options(selectinload(UserModel.legal_guardians))
            .where(UserModel.public_id == user.public_id)
        )
    ).scalar_one()
    assert {g.public_id for g in updated.legal_guardians} == {guardian.public_id}


@pytest.mark.asyncio
async def test_user_manager_modify_legal_wards_clear(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
) -> None:
    ward = await user_factory()
    user = await user_factory(legal_wards=[ward])

    ops: list[JSONPathOperation] = [
        {
            "op": "replace",
            "path": "/legal_wards",
            "value": [],
        }
    ]
    await SQLAlchemyUserManager(db_session).modify(user.public_id, ops)

    updated = (
        await db_session.execute(
            select(UserModel)
            .options(selectinload(UserModel.legal_wards))
            .where(UserModel.public_id == user.public_id)
        )
    ).scalar_one()
    assert updated.legal_wards == []


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
