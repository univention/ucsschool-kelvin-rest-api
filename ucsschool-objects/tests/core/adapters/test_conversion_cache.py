# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""The conversion cache must be invisible: same output, same object graph.

These tests pin the two properties that make it safe: what comes out is
unchanged, and no two conversions share anything they did not share before.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import load_only, raiseload
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import (
    ConversionCache,
    to_group,
    to_role,
    to_school,
    to_user,
)
from ucsschool_objects.core.domain.json import to_json
from ucsschool_objects.core.domain.models import DomainObject, is_loaded
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _school(session: AsyncSession, name: str = "DEMOSCHOOL") -> SchoolModel:
    school = SchoolModel(
        public_id=uuid.uuid4(),
        record_uid=f"record-{name}",
        source_uid="source",
        name=name,
        display_name=name,
        educational_servers=[f"{name}.edu.example"],
        administrative_servers=[],
        udm_properties={"description": name},
    )
    session.add(school)
    await session.flush()
    return school


async def _role(session: AsyncSession, name: str) -> RoleModel:
    role = RoleModel(public_id=uuid.uuid4(), name=name, display_name={"en": name})
    session.add(role)
    await session.flush()
    return role


async def _group(session: AsyncSession, school: SchoolModel, name: str) -> GroupModel:
    group = GroupModel(
        public_id=uuid.uuid4(),
        record_uid=f"record-{name}",
        source_uid="source",
        name=name,
        display_name=name,
        school=school,
        udm_properties={},
    )
    group.roles = []
    group.members = []
    group.member_roles = []
    group.allowed_email_senders_users = []
    group.allowed_email_senders_groups = []
    session.add(group)
    await session.flush()
    return group


async def _user(
    session: AsyncSession, school: SchoolModel, role: RoleModel, group: GroupModel, name: str
) -> UserModel:
    user = UserModel(
        public_id=uuid.uuid4(),
        record_uid=f"record-{name}",
        source_uid="source",
        name=name,
        firstname="First",
        lastname=name,
        active=True,
        udm_properties={"uidNumber": 2000},
    )
    user.legal_wards = []
    user.legal_guardians = []
    user.school_memberships = []
    membership = SchoolMembershipModel(school=school, is_primary=True)
    membership.groups = [group]
    membership.roles = [role]
    user.school_memberships.append(membership)
    session.add(user)
    await session.flush()
    return user


async def test_cached_conversion_matches_uncached(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    role = await _role(db_session, "student")
    group = await _group(db_session, school, "DEMOSCHOOL-1a")
    models = [await _user(db_session, school, role, group, f"user{i}") for i in range(3)]

    uncached = [to_user(model) for model in models]
    cache = ConversionCache()
    cached = [to_user(model, cache) for model in models]

    assert [to_json(user) for user in cached] == [to_json(user) for user in uncached]


async def test_cache_hands_out_distinct_objects_per_conversion(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    role = await _role(db_session, "student")
    group = await _group(db_session, school, "DEMOSCHOOL-1a")
    first_model = await _user(db_session, school, role, group, "first")
    second_model = await _user(db_session, school, role, group, "second")

    cache = ConversionCache()
    first = next(iter(to_user(first_model, cache).school_memberships.values()))
    second = next(iter(to_user(second_model, cache).school_memberships.values()))

    assert first.school is not second.school
    assert first.school.educational_servers is not second.school.educational_servers
    assert {id(g) for g in first.groups}.isdisjoint({id(g) for g in second.groups})
    assert {id(g.school) for g in first.groups}.isdisjoint({id(g.school) for g in second.groups})
    assert {id(r) for r in first.roles}.isdisjoint({id(r) for r in second.roles})
    # to_school hands out the ORM instance's own dict, cached or not.
    assert first.school.udm_properties is second.school.udm_properties


async def test_a_change_to_one_conversion_does_not_reach_the_next(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    cache = ConversionCache()

    first = to_school(school, cache)
    first.name = "CHANGED"
    first.educational_servers.add("extra.example")

    second = to_school(school, cache)
    assert second.name == "DEMOSCHOOL"
    assert second.educational_servers == {"DEMOSCHOOL.edu.example"}


async def test_roles_and_groups_are_served_from_the_cache(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    role_model = await _role(db_session, "student")
    group_model = await _group(db_session, school, "DEMOSCHOOL-1a")
    cache = ConversionCache()

    assert to_json(to_role(role_model, cache)) == to_json(to_role(role_model, cache))
    assert to_json(to_group(group_model, cache)) == to_json(to_group(group_model, cache))
    assert cache.roles[role_model] is not None
    assert cache.groups[group_model] is not None


async def test_a_projected_school_stays_projected_through_the_cache(
    db_session: AsyncSession,
) -> None:
    """A LoadSpec projection leaves attributes unloaded; a copy must not invent them."""
    await _school(db_session)
    db_session.expunge_all()
    model = (
        await db_session.execute(
            select(SchoolModel).options(load_only(SchoolModel.public_id, SchoolModel.name))
        )
    ).scalar_one()
    cache = ConversionCache()

    built = to_school(model, cache)
    copied = to_school(model, cache)

    assert to_json(built) == to_json(copied)
    for attribute in ("educational_servers", "administrative_servers", "udm_properties"):
        assert not is_loaded(copied, attribute)


async def test_a_group_with_unloaded_relations_stays_that_way_through_the_cache(
    db_session: AsyncSession,
) -> None:
    school = await _school(db_session)
    await _group(db_session, school, "DEMOSCHOOL-1a")
    db_session.expunge_all()
    # Group.school is lazy="selectin", so it takes a raiseload() to leave it out.
    model = (
        await db_session.execute(select(GroupModel).options(raiseload(GroupModel.school)))
    ).scalar_one()
    cache = ConversionCache()

    built = to_group(model, cache)
    copied = to_group(model, cache)

    assert to_json(built) == to_json(copied)
    for relation in ("school", "roles", "member_roles", "members", "allowed_email_senders_users"):
        assert not is_loaded(copied, relation)


async def test_a_row_converted_past_the_memo_is_not_stored(db_session: AsyncSession) -> None:
    """A search yields each row once, so memoizing it would only cost a copy."""
    school_model = await _school(db_session)
    role_model = await _role(db_session, "student")
    cache = ConversionCache()

    school = to_school(school_model, cache, memoize=False)
    role = to_role(role_model, cache, memoize=False)

    assert to_json(school) == to_json(to_school(school_model))
    assert to_json(role) == to_json(to_role(role_model))
    assert school_model not in cache.schools
    assert role_model not in cache.roles


async def test_a_row_converted_past_the_memo_still_memoizes_its_relations(
    db_session: AsyncSession,
) -> None:
    school_model = await _school(db_session)
    group_model = await _group(db_session, school_model, "DEMOSCHOOL-1a")
    cache = ConversionCache()

    group = to_group(group_model, cache, memoize=False)

    assert to_json(group) == to_json(to_group(group_model))
    assert group_model not in cache.groups
    assert school_model in cache.schools


def _shared_fields(first: DomainObject, second: DomainObject) -> set[str]:
    """The fields where two conversions of one row handed out the same object."""
    return {
        field for field in first.__serialize_fields__ if getattr(first, field) is getattr(second, field)
    }


async def test_a_copy_shares_exactly_what_a_fresh_conversion_shares(
    db_session: AsyncSession,
) -> None:
    """Field-driven, so a field the copy does not know about fails here first.

    Each ``_clone_*`` names the attributes it rebuilds. Add a mutable field to
    School, Role or Group and the copy would hand out the original's object,
    quietly tying two conversions of one row together.
    """
    school_model = await _school(db_session)
    role_model = await _role(db_session, "student")
    group_model = await _group(db_session, school_model, "DEMOSCHOOL-1a")
    cache = ConversionCache()

    assert _shared_fields(
        to_school(school_model, cache), to_school(school_model, cache)
    ) == _shared_fields(to_school(school_model), to_school(school_model))
    assert _shared_fields(to_role(role_model, cache), to_role(role_model, cache)) == _shared_fields(
        to_role(role_model), to_role(role_model)
    )
    assert _shared_fields(to_group(group_model, cache), to_group(group_model, cache)) == _shared_fields(
        to_group(group_model), to_group(group_model)
    )
