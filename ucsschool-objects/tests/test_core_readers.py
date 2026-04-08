from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from ucsschool_objects.core import UNLOADED, Filter, LoadSpec, Operator, SearchQuery, SortSpec
from ucsschool_objects.core.adapters import (
    SqlAlchemyGroupReader,
    SqlAlchemySchoolReader,
    SqlAlchemyUserReader,
)
from ucsschool_objects.core.adapters.sqlalchemy_readers import (
    _build_expression,
    _coerce_date,
    _iter_filters,
)
from ucsschool_objects.core.domain import Group, School
from ucsschool_objects.core.query import And, Or
from ucsschool_objects.database_models import GroupMemberAssociation, User as UserModel

if TYPE_CHECKING:
    from tests.test_types import GroupFactory, SchoolFactory, SchoolMembershipFactory, UserFactory


def test_user_reader_get_keeps_relationships_unloaded(
    db_session: Session,
    user_factory: UserFactory,
    school_factory: SchoolFactory,
    school_membership_factory: SchoolMembershipFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-1")
    user = user_factory(name="user-1")
    membership = school_membership_factory(user=user, school=school, is_primary=True)
    group = group_factory(name="group-1", school=school)
    db_session.add(GroupMemberAssociation(group_id=group.id, school_membership_id=membership.id))
    db_session.flush()

    reader = SqlAlchemyUserReader(db_session)

    loaded = asyncio.run(reader.get(user.public_id))

    assert loaded is not None
    assert loaded.school is UNLOADED
    assert loaded.groups is UNLOADED


def test_user_reader_get_with_explicit_load_spec(
    db_session: Session,
    user_factory: UserFactory,
    school_factory: SchoolFactory,
    school_membership_factory: SchoolMembershipFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-2")
    user = user_factory(name="user-2")
    membership = school_membership_factory(user=user, school=school, is_primary=True)
    group = group_factory(name="group-2", school=school)
    db_session.add(GroupMemberAssociation(group_id=group.id, school_membership_id=membership.id))
    db_session.flush()

    reader = SqlAlchemyUserReader(db_session)

    loaded = asyncio.run(reader.get(user.public_id, load=LoadSpec.only("school", "groups")))

    assert loaded is not None
    assert loaded.school is not UNLOADED
    assert loaded.school is not None
    assert loaded.groups is not UNLOADED
    loaded_school = cast(School, loaded.school)
    loaded_groups = cast(tuple[Group, ...], loaded.groups)
    assert loaded_school.name == "school-2"
    assert [group.name for group in loaded_groups] == ["group-2"]


def test_user_reader_search_with_filter_sort_and_pagination(
    db_session: Session,
    user_factory: UserFactory,
) -> None:
    user_factory(name="anna")
    user_factory(name="bert")
    user_factory(name="carla")

    reader = SqlAlchemyUserReader(db_session)

    users = asyncio.run(
        reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.LIKE, value="%a%")),
            sort_by=(SortSpec("name", ascending=False),),
            limit=1,
            offset=0,
        )
    )

    assert [user.name for user in users] == ["carla"]


def test_group_reader_loads_school_only_when_requested(
    db_session: Session,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-3")
    group = group_factory(name="group-3", school=school)

    reader = SqlAlchemyGroupReader(db_session)

    unloaded = asyncio.run(reader.get(group.public_id))
    loaded = asyncio.run(reader.get(group.public_id, load=LoadSpec.only("school")))

    assert unloaded is not None
    assert unloaded.school is UNLOADED
    assert loaded is not None
    assert loaded.school is not UNLOADED
    assert loaded.school is not None
    loaded_school = cast(School, loaded.school)
    assert loaded_school.name == "school-3"


def test_school_reader_search_eq_and_default_sort(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="zeta")
    alpha = school_factory(name="alpha")

    reader = SqlAlchemySchoolReader(db_session)

    schools = asyncio.run(
        reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="alpha")))
    )

    assert len(schools) == 1
    assert schools[0].public_id == alpha.public_id


def test_school_reader_get_existing_and_missing(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school = school_factory(name="school-4")
    reader = SqlAlchemySchoolReader(db_session)

    loaded = asyncio.run(reader.get(school.public_id))
    missing = asyncio.run(reader.get(uuid4()))

    assert loaded is not None
    assert loaded.name == "school-4"
    assert missing is None


def test_group_reader_get_missing_and_search_by_school_fields(
    db_session: Session,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-5")
    group_factory(name="group-a", school=school)
    group_factory(name="group-b", school=school)
    reader = SqlAlchemyGroupReader(db_session)

    missing = asyncio.run(reader.get(uuid4()))
    groups = asyncio.run(
        reader.search(
            SearchQuery(
                where=And(
                    clauses=(
                        Filter(field="school_name", op=Operator.EQ, value="school-5"),
                        Or(clauses=(Filter(field="name", op=Operator.EQ, value="group-a"),)),
                    )
                )
            ),
            load=LoadSpec.only("school"),
        )
    )

    assert missing is None
    assert [group.name for group in groups] == ["group-a"]
    assert groups[0].school is not UNLOADED


def test_group_reader_search_without_query_uses_default_sort(
    db_session: Session,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-6")
    first = group_factory(name="group-c", school=school)
    second = group_factory(name="group-d", school=school)
    reader = SqlAlchemyGroupReader(db_session)

    groups = asyncio.run(reader.search())

    assert [group.public_id for group in groups] == sorted([first.public_id, second.public_id])


def test_group_reader_search_with_non_school_filter_does_not_join_school(
    db_session: Session,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-6b")
    group_factory(name="group-e", school=school)
    group_factory(name="group-f", school=school)
    reader = SqlAlchemyGroupReader(db_session)

    groups = asyncio.run(
        reader.search(SearchQuery(where=Filter(field="name", op=Operator.EQ, value="group-f")))
    )

    assert [group.name for group in groups] == ["group-f"]


def test_user_reader_get_missing_and_without_primary_school(
    db_session: Session,
    user_factory: UserFactory,
    school_factory: SchoolFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> None:
    user = user_factory(name="user-without-primary")
    school = school_factory(name="school-7")
    school_membership_factory(user=user, school=school, is_primary=False)
    reader = SqlAlchemyUserReader(db_session)

    loaded = asyncio.run(reader.get(user.public_id, load=LoadSpec.only("school")))
    missing = asyncio.run(reader.get(uuid4()))

    assert loaded is not None
    assert loaded.school is None
    assert missing is None


def test_user_reader_search_with_in_operator_and_group_loading(
    db_session: Session,
    user_factory: UserFactory,
    school_factory: SchoolFactory,
    school_membership_factory: SchoolMembershipFactory,
    group_factory: GroupFactory,
) -> None:
    school = school_factory(name="school-8")
    anna = user_factory(name="anna-in")
    bert = user_factory(name="bert-in")
    anna_membership = school_membership_factory(user=anna, school=school, is_primary=True)
    bert_membership = school_membership_factory(user=bert, school=school, is_primary=True)
    group = group_factory(name="group-in", school=school)
    db_session.add(GroupMemberAssociation(group_id=group.id, school_membership_id=anna_membership.id))
    db_session.add(GroupMemberAssociation(group_id=group.id, school_membership_id=bert_membership.id))
    db_session.flush()

    reader = SqlAlchemyUserReader(db_session)
    users = asyncio.run(
        reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.IN, value=["anna-in", "bert-in"])),
            sort_by=(SortSpec("name"),),
            load=LoadSpec.only("groups"),
        )
    )

    assert [user.name for user in users] == ["anna-in", "bert-in"]
    assert users[0].groups is not UNLOADED


def test_query_helper_branches() -> None:
    field_map = {"name": UserModel.name, "active": UserModel.active}

    assert _coerce_date(None) is None
    assert _coerce_date("invalid") is None
    assert _coerce_date(date(2026, 4, 8)) == date(2026, 4, 8)

    and_expr = And(
        clauses=(
            Filter(field="name", op=Operator.EQ, value="alpha"),
            Filter(field="active", op=Operator.EQ, value=True),
        )
    )
    or_expr = Or(clauses=(Filter(field="name", op=Operator.EQ, value="alpha"),))

    assert str(_build_expression(and_expr, field_map))
    assert str(_build_expression(or_expr, field_map))
    assert list(_iter_filters(and_expr))[0].field == "name"

    with pytest.raises(ValueError, match="LIKE operator requires a string value"):
        _build_expression(Filter(field="name", op=Operator.LIKE, value=123), field_map)

    with pytest.raises(ValueError, match="Unsupported operator"):
        _build_expression(Filter(field="name", op=cast(Operator, "bad"), value="alpha"), field_map)

    with pytest.raises(ValueError, match="AND query requires at least one clause"):
        _build_expression(And(clauses=()), field_map)

    with pytest.raises(ValueError, match="OR query requires at least one clause"):
        _build_expression(Or(clauses=()), field_map)


def test_search_query_in_operator_requires_iterable(
    db_session: Session, user_factory: UserFactory
) -> None:
    user_factory(name="alex")
    reader = SqlAlchemyUserReader(db_session)

    with pytest.raises(ValueError, match="IN operator requires an iterable value"):
        asyncio.run(reader.search(SearchQuery(where=Filter(field="name", op=Operator.IN, value="alex"))))
