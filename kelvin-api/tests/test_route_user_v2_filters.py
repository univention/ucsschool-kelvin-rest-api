# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the query the v2 user search builds from its parameters.

The filter tree is asserted directly instead of through HTTP; the round trip
over the API is covered by the integration tests in ``test_route_user.py``.
"""

from collections.abc import Sequence

import pytest
from fastapi import HTTPException
from ucsschool_objects import And, AnyRelated, Filter, Operator, Or, SearchQuery

from ucsschool.kelvin.routers.v2._filters import ucsschool_role_filter
from ucsschool.kelvin.routers.v2.user import _build_query


def _query(
    names: Sequence[str] | None,
    school: str | None = None,
    ucsschool_roles: Sequence[str] | None = None,
) -> SearchQuery | None:
    return _build_query(
        school=school,
        name=names,
        ucsschool_roles=ucsschool_roles,
        firstname=None,
        lastname=None,
        email=None,
        record_uid=None,
        source_uid=None,
        birthday=None,
        expiration_date=None,
        disabled=None,
    )


def test_no_name_yields_no_query() -> None:
    assert _query(None) is None


def test_empty_values_are_ignored() -> None:
    """``?name=`` filtered nothing before the parameter accepted a list."""
    assert _query([""]) is None


def test_single_name_matches_case_insensitively() -> None:
    assert _query(["alice"]) == SearchQuery(
        where=Filter(field="name", op=Operator.IN_CI, value=("alice",))
    )


def test_several_names_share_one_set_lookup() -> None:
    """The point of the list: one comparison for all values, not one per value."""
    assert _query(["alice", "bob", "carol"]) == SearchQuery(
        where=Filter(field="name", op=Operator.IN_CI, value=("alice", "bob", "carol"))
    )


def test_wildcard_value_stays_a_pattern_match() -> None:
    assert _query(["ali*"]) == SearchQuery(
        where=Filter(field="name", op=Operator.MATCHES_CI, value="ali*")
    )


def test_wildcards_and_plain_values_are_combined() -> None:
    assert _query(["alice", "b*b"]) == SearchQuery(
        where=Or(
            clauses=(
                Filter(field="name", op=Operator.IN_CI, value=("alice",)),
                Filter(field="name", op=Operator.MATCHES_CI, value="b*b"),
            )
        )
    )


def test_names_combine_with_other_parameters() -> None:
    query = _query(["alice", "bob"], school="DEMOSCHOOL")

    assert query is not None
    assert isinstance(query.where, And)
    assert Filter(field="name", op=Operator.IN_CI, value=("alice", "bob")) in query.where.clauses


def _school_role(value: str) -> AnyRelated:
    return AnyRelated(Filter(field="school_roles", op=Operator.MATCHES_CI, value=value))


def _role_at_school(role: str, school: str) -> AnyRelated:
    return AnyRelated(
        And(
            clauses=(
                Filter(field="roles.name", op=Operator.MATCHES_CI, value=role),
                Filter(field="schools.name", op=Operator.MATCHES_CI, value=school),
            )
        )
    )


def test_single_ucsschool_role_matches_role_and_school_of_one_membership() -> None:
    assert _query(None, ucsschool_roles=["teacher:school:DEMOSCHOOL"]) == SearchQuery(
        where=_role_at_school("teacher", "DEMOSCHOOL")
    )


def test_all_ucsschool_roles_must_match() -> None:
    assert _query(None, ucsschool_roles=["teacher:school:DEMOSCHOOL", "staff:school:*"]) == SearchQuery(
        where=And(clauses=(_role_at_school("teacher", "DEMOSCHOOL"), _role_at_school("staff", "*")))
    )


def test_repeated_ucsschool_roles_count_once() -> None:
    assert _query(None, ucsschool_roles=["teacher:school:DEMOSCHOOL"] * 2) == SearchQuery(
        where=_role_at_school("teacher", "DEMOSCHOOL")
    )


def test_up_to_20_different_ucsschool_roles_are_accepted() -> None:
    values = [f"teacher:school:school{index}" for index in range(20)]

    query = _query(None, ucsschool_roles=[*values, *values])

    assert query is not None
    assert isinstance(query.where, And)
    assert len(query.where.clauses) == 20


def test_more_than_20_different_ucsschool_roles_are_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _query(None, ucsschool_roles=[f"teacher:school:school{index}" for index in range(21)])

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    ("value", "role", "school"),
    [
        pytest.param("*:school:DEMOSCHOOL", "*", "DEMOSCHOOL", id="wildcard-role"),
        pytest.param("TEACHER:SCHOOL:demoschool", "TEACHER", "demoschool", id="case"),
        pytest.param("teacher:sch*:DEMO*", "teacher", "DEMO*", id="wildcard-context-type"),
        pytest.param("teacher:*:DEMOSCHOOL", "teacher", "DEMOSCHOOL", id="any-context-type"),
    ],
)
def test_ucsschool_role_with_three_parts_is_split(value: str, role: str, school: str) -> None:
    assert ucsschool_role_filter(value) == _role_at_school(role, school)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param("teacher*DEMOSCHOOL", id="wildcard-across-parts"),
        pytest.param("*", id="wildcard-only"),
        pytest.param("teacher:exam:DEMOSCHOOL", id="other-context-type"),
        pytest.param("a:b:c:d", id="four-parts"),
    ],
)
def test_other_ucsschool_roles_match_the_whole_entry(value: str) -> None:
    assert ucsschool_role_filter(value) == _school_role(value)


def test_ucsschool_roles_combine_with_other_parameters() -> None:
    query = _query(["alice"], school="DEMOSCHOOL", ucsschool_roles=["student:school:DEMOSCHOOL"])

    assert query is not None
    assert isinstance(query.where, And)
    assert _role_at_school("student", "DEMOSCHOOL") in query.where.clauses
    assert Filter(field="name", op=Operator.IN_CI, value=("alice",)) in query.where.clauses
