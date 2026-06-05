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
    LIKE = "like"
    ILIKE = "ilike"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


FilterScalarValue: TypeAlias = str | int | float | bool | date | datetime | Decimal | UUID | None
FilterInValue: TypeAlias = Iterable[FilterScalarValue]
FilterValue: TypeAlias = FilterScalarValue | FilterInValue


@dataclass(frozen=True)
class Filter:
    """Single field constraint.

    Example: field="name", op=Operator.LIKE, value="Miller%".
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
