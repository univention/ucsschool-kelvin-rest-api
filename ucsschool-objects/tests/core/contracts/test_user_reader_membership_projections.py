from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlalchemy import SQLAlchemyUserReader
from ucsschool_objects.core.domain import (
    Filter,
    LoadSpec,
    Operator,
    SearchQuery,
    UnloadedType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncGroupFactory as GroupFactory,
        AsyncRoleFactory as RoleFactory,
        AsyncSchoolFactory as SchoolFactory,
        AsyncSchoolMembershipFactory as SchoolMembershipFactory,
        AsyncUserFactory as UserFactory,
    )


@pytest.mark.asyncio
async def test_primary_school_via_reader(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> None:
    school = await school_factory(name="primary_school")
    other = await school_factory(name="other_school")
    user = await user_factory(name="primaryuser")
    await school_membership_factory(user=user, school=school, is_primary=True)
    await school_membership_factory(user=user, school=other, is_primary=False)

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="primaryuser")),
            load=LoadSpec.from_relations("school_memberships"),
        )
    )
    assert len(results) == 1
    loaded_user = results[0]
    assert loaded_user.primary_school is not None
    assert not isinstance(loaded_user.primary_school, UnloadedType)
    assert loaded_user.primary_school.name == "primary_school"


@pytest.mark.asyncio
async def test_primary_school_raises_when_no_primary(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> None:
    school = await school_factory(name="non_primary_school")
    user = await user_factory(name="noprimaryuser")
    await school_membership_factory(user=user, school=school, is_primary=False)

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="noprimaryuser")),
            load=LoadSpec.from_relations("school_memberships"),
        )
    )
    assert len(results) == 1
    with pytest.raises(ValueError, match="no primary school"):
        _ = results[0].primary_school


@pytest.mark.asyncio
async def test_groups_flat_via_reader(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
    group_factory: GroupFactory,
) -> None:
    school = await school_factory(name="groupschool")
    user = await user_factory(name="groupuser")
    g1 = await group_factory(school=school, name="group_one")
    g2 = await group_factory(school=school, name="group_two")
    membership = await school_membership_factory(user=user, school=school, is_primary=True)
    await db_session.refresh(membership, attribute_names=["groups"])
    membership.groups.extend([g1, g2])
    await db_session.flush()

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="groupuser")),
            load=LoadSpec.from_relations("school_memberships", "groups"),
        )
    )
    assert len(results) == 1
    loaded_user = results[0]
    assert not isinstance(loaded_user.groups, UnloadedType)
    group_names = {g.name for g in loaded_user.groups}
    assert group_names == {"group_one", "group_two"}


@pytest.mark.asyncio
async def test_roles_accessible_via_school_memberships(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
    role_factory: RoleFactory,
) -> None:
    school = await school_factory(name="school_with_roles")
    user = await user_factory(name="roleuser")
    role = await role_factory(name="teacher_role")
    membership = await school_membership_factory(user=user, school=school, is_primary=True)
    await db_session.refresh(membership, attribute_names=["roles"])
    membership.roles.append(role)
    await db_session.flush()

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="roleuser")),
            load=LoadSpec.from_relations("school_memberships", "roles"),
        )
    )
    assert len(results) == 1
    loaded_user = results[0]
    assert not isinstance(loaded_user.school_memberships, UnloadedType)
    assert len(loaded_user.school_memberships) == 1
    sm = loaded_user.school_memberships[0]
    assert not isinstance(sm.roles, UnloadedType)
    assert len(sm.roles) == 1
    assert sm.roles[0].name == "teacher_role"


@pytest.mark.asyncio
async def test_legal_wards_via_reader(
    db_session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    guardian = await user_factory(name="guardian_user")
    ward = await user_factory(name="ward_user")
    await db_session.refresh(guardian, attribute_names=["legal_wards"])
    guardian.legal_wards.append(ward)
    await db_session.flush()

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="guardian_user")),
            load=LoadSpec.from_relations("legal_wards"),
        )
    )

    assert len(results) == 1
    loaded_user = results[0]
    assert not isinstance(loaded_user.legal_wards, UnloadedType)
    assert {u.name for u in loaded_user.legal_wards} == {"ward_user"}
    assert isinstance(loaded_user.legal_guardians, UnloadedType)
    related_user = loaded_user.legal_wards[0]
    assert isinstance(related_user.school_memberships, UnloadedType)
    assert isinstance(related_user.legal_wards, UnloadedType)
    assert isinstance(related_user.legal_guardians, UnloadedType)


@pytest.mark.asyncio
async def test_legal_guardians_via_reader(
    db_session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    guardian = await user_factory(name="guardian_two")
    ward = await user_factory(name="ward_two")
    await db_session.refresh(ward, attribute_names=["legal_guardians"])
    ward.legal_guardians.append(guardian)
    await db_session.flush()

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="ward_two")),
            load=LoadSpec.from_relations("legal_guardians"),
        )
    )

    assert len(results) == 1
    loaded_user = results[0]
    assert not isinstance(loaded_user.legal_guardians, UnloadedType)
    assert {u.name for u in loaded_user.legal_guardians} == {"guardian_two"}
    assert isinstance(loaded_user.legal_wards, UnloadedType)
    related_user = loaded_user.legal_guardians[0]
    assert isinstance(related_user.school_memberships, UnloadedType)
    assert isinstance(related_user.legal_wards, UnloadedType)
    assert isinstance(related_user.legal_guardians, UnloadedType)
