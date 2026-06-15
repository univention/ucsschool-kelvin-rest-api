"""Public query model for filtering, logical composition, and sorting.

The types in this module define a small expression tree used by read APIs.
Adapters can translate these structures into backend-specific query languages.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TypeAlias
from uuid import UUID


class Operator(str, Enum):
    """Supported comparison operators for filter expressions."""

    EQ = "eq"
    NE = "ne"
    IN = "in"
    MATCHES = "matches"
    MATCHES_CI = "matches_ci"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    """Membership in a multi-valued (JSON array) field; equality on scalars."""


FilterScalarValue: TypeAlias = str | int | float | bool | date | datetime | Decimal | UUID | None
FilterInValue: TypeAlias = Iterable[FilterScalarValue]
FilterValue: TypeAlias = FilterScalarValue | FilterInValue


@dataclass(frozen=True)
class Filter:
    """Single field constraint.

    Example: field="name", op=Operator.MATCHES, value="Miller*".
    """

    field: str
    op: Operator
    value: FilterValue


@dataclass(frozen=True)
class And:
    """Logical conjunction over all child clauses."""

    clauses: tuple[QueryExpr, ...]


@dataclass(frozen=True)
class Or:
    """Logical disjunction over child clauses."""

    clauses: tuple[QueryExpr, ...]


@dataclass(frozen=True)
class Not:
    """Logical negation of a single clause."""

    clause: QueryExpr


QueryExpr: TypeAlias = Filter | And | Or | Not


@dataclass(frozen=True)
class SortSpec:
    """Sort instruction for a field.

    Attributes:
        field: Field name to sort by.
        ascending: True for ascending order, False for descending order.
    """

    field: str
    ascending: bool = True


@dataclass(frozen=True)
class SearchQuery:
    """Container for search criteria.

    Attributes:
        where: Optional query expression tree used to filter results.
    """

    where: QueryExpr | None = None


def make_wildcard_filter(
    field: str,
    user_value: str,
    *,
    case_insensitive: bool = False,
) -> Filter:
    """Create a pattern-matching filter using ``*`` as wildcard syntax.

    The domain stores user intent, not backend-specific pattern syntax.
    Storage adapters are responsible for translating ``*`` into the
    appropriate backend wildcard representation and escaping backend-specific
    metacharacters.

    Args:
        field: The field name to filter on (e.g., "name", "school.name").
        user_value: User-provided search value. ``*`` means wildcard matching.
            All other characters are preserved as entered and translated by
            the storage adapter.
        case_insensitive: When ``True``, create a case-insensitive pattern
            match filter.

    Returns:
        A Filter with ``Operator.MATCHES`` or ``Operator.MATCHES_CI`` and the
        raw user pattern.

    Raises:
        TypeError: If user_value is not a string.
        ValueError: If field is empty or not a string.

    Examples:
        >>> # User searches for users named literally "50%"
        >>> f = make_wildcard_filter("name", "50%")
        >>> f.value
        '50%'

        >>> # User searches for users matching "test*" wildcard
        >>> f = make_wildcard_filter("name", "test*")
        >>> f.value
        'test*'

        >>> # User searches case-insensitively for users matching "test*"
        >>> f = make_wildcard_filter("name", "test*", case_insensitive=True)
        >>> f.op
        <Operator.MATCHES_CI: 'matches_ci'>

        >>> # User searches with both wildcard and literal special chars
        >>> f = make_wildcard_filter("name", "test*_end")
        >>> f.value
        'test*_end'
    """
    if not isinstance(user_value, str):
        raise TypeError(f"user_value must be str, got {type(user_value).__name__}")
    if not isinstance(field, str) or not field:
        raise ValueError("field must be a non-empty string")

    operator = Operator.MATCHES_CI if case_insensitive else Operator.MATCHES
    return Filter(field=field, op=operator, value=user_value)
