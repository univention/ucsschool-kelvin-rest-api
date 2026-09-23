# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the query both v2 group collections build from their parameters.

The filter tree is asserted directly instead of through HTTP; the round trip
over the API is covered by the integration tests in ``test_route_school_class.py``
and ``test_route_workgroup.py``. How plain and wildcard values are combined is
the shared ``name_filter``'s, tested through the user search in
``test_route_user_v2_filters.py``; what is asserted here is the group part,
the school and its prefix on every value.
"""

from collections.abc import Sequence

from ucsschool_objects import And, Filter, Operator, Or, SearchQuery

from ucsschool.kelvin.routers.v2._filters import group_search_query

_SCHOOL = Filter(field="school.name", op=Operator.EQ, value="DEMOSCHOOL")


def _query(names: Sequence[str] | None) -> SearchQuery:
    return group_search_query("DEMOSCHOOL", names)


def test_no_name_asks_for_the_whole_school() -> None:
    assert _query(None) == SearchQuery(where=_SCHOOL)


def test_empty_values_are_ignored() -> None:
    """``?name=`` narrowed nothing before the parameter accepted a list."""
    assert _query([""]) == SearchQuery(where=_SCHOOL)


def test_a_name_is_matched_with_its_school_prefix() -> None:
    """Stored names carry the school, the parameter does not."""
    assert _query(["1a"]) == SearchQuery(
        where=And(
            clauses=(
                _SCHOOL,
                Filter(field="name", op=Operator.IN_CI, value=("DEMOSCHOOL-1a",)),
            )
        )
    )


def test_wildcards_and_plain_values_are_combined() -> None:
    assert _query(["1a", "2*"]) == SearchQuery(
        where=And(
            clauses=(
                _SCHOOL,
                Or(
                    clauses=(
                        Filter(field="name", op=Operator.IN_CI, value=("DEMOSCHOOL-1a",)),
                        Filter(field="name", op=Operator.MATCHES_CI, value="DEMOSCHOOL-2*"),
                    )
                ),
            )
        )
    )
