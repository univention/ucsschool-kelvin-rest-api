from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TypeAlias


class Operator(str, Enum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    LIKE = "like"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


FilterScalarValue: TypeAlias = str | int | float | bool | date | datetime | Decimal | None
FilterInValue: TypeAlias = Iterable[FilterScalarValue]
FilterValue: TypeAlias = FilterScalarValue | FilterInValue


@dataclass(frozen=True)
class Filter:
    field: str
    op: Operator
    value: FilterValue


@dataclass(frozen=True)
class And:
    clauses: tuple["QueryExpr", ...]


@dataclass(frozen=True)
class Or:
    clauses: tuple["QueryExpr", ...]


@dataclass(frozen=True)
class Not:
    clause: "QueryExpr"


QueryExpr: TypeAlias = Filter | And | Or | Not


@dataclass(frozen=True)
class SortSpec:
    field: str
    ascending: bool = True


@dataclass(frozen=True)
class SearchQuery:
    where: QueryExpr | None = None
