# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import re
from collections.abc import Sequence

from ucsschool_objects import (
    And,
    AnyRelated,
    Filter,
    Operator,
    Or,
    QueryExpr,
    SearchQuery,
    make_wildcard_filter,
)


def str_filter(field: str, value: str, *, case_insensitive: bool = False) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    if case_insensitive:
        return make_wildcard_filter(field, value, case_insensitive=True)
    if "*" in value:
        return make_wildcard_filter(field, value)
    return Filter(field=field, op=Operator.EQ, value=value)


def name_filter(field: str, values: Sequence[str]) -> QueryExpr:
    """Filter matching any of ``values``, with the same semantics per value.

    Values without a wildcard are collected into a single case-insensitive
    ``IN``, so that asking for hundreds of names stays one set lookup instead of
    one pattern match per value.
    """
    plain = tuple(value for value in values if "*" not in value)
    clauses: list[QueryExpr] = [
        make_wildcard_filter(field, value, case_insensitive=True) for value in values if "*" in value
    ]
    if plain:
        clauses.insert(0, Filter(field=field, op=Operator.IN_CI, value=plain))
    if len(clauses) == 1:
        return clauses[0]
    return Or(clauses=tuple(clauses))


def _glob_matches(pattern: str, text: str) -> bool:
    regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.fullmatch(regex, text, re.IGNORECASE) is not None


def ucsschool_role_filter(value: str) -> AnyRelated:
    parts = value.split(":")
    if len(parts) == 3 and _glob_matches(parts[1], "school"):
        role, _, school = parts
        return AnyRelated(
            And(
                clauses=(
                    make_wildcard_filter("roles.name", role, case_insensitive=True),
                    make_wildcard_filter("schools.name", school, case_insensitive=True),
                )
            )
        )
    return AnyRelated(make_wildcard_filter("school_roles", value, case_insensitive=True))


def group_search_query(
    school: str, names: Sequence[str] | None, *, role: str | None = None
) -> SearchQuery:
    """The query behind a group collection: one school, optionally narrowed by name.

    Stored group names carry the school as a prefix, so it is applied per value
    before they are folded into one lookup. Both group collections build it,
    each with its own ``role``. Asking for all the names at once is what keeps resolving the
    groups of a user list to one request instead of one per group.

    ``role`` keeps school classes and workgroups apart in the query itself. A
    page cut by ``limit`` must not lose groups to a filter applied afterwards.
    """
    clauses: list[QueryExpr] = [Filter(field="school.name", op=Operator.EQ, value=school)]
    wanted = [name for name in names or () if name]
    if wanted:
        clauses.append(name_filter("name", [f"{school}-{name}" for name in wanted]))
    if role:
        clauses.append(Filter(field="roles.name", op=Operator.EQ, value=role))
    return SearchQuery(where=And(clauses=tuple(clauses)) if len(clauses) > 1 else clauses[0])
