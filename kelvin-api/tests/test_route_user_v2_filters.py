# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the query the v2 user search builds from its parameters.

The filter tree is asserted directly instead of through HTTP; the round trip
over the API is covered by the integration tests in ``test_route_user.py``.
"""

from collections.abc import Sequence

from ucsschool_objects import And, Filter, Operator, Or, SearchQuery

from ucsschool.kelvin.routers.v2.user import _build_query


def _query(names: Sequence[str] | None, school: str | None = None) -> SearchQuery | None:
    return _build_query(
        school=school,
        name=names,
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
