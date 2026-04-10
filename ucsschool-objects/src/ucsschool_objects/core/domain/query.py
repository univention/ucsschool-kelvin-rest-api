from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias


class Operator(str, Enum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    LIKE = "like"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


@dataclass(frozen=True, slots=True)
class Filter:
    field: str
    op: Operator
    value: Any


@dataclass(frozen=True, slots=True)
class And:
    clauses: tuple["QueryExpr", ...]


@dataclass(frozen=True, slots=True)
class Or:
    clauses: tuple["QueryExpr", ...]


@dataclass(frozen=True, slots=True)
class Not:
    clause: "QueryExpr"


QueryExpr: TypeAlias = Filter | And | Or | Not


@dataclass(frozen=True, slots=True)
class SortSpec:
    field: str
    ascending: bool = True


@dataclass(frozen=True, slots=True)
class SearchQuery:
    where: QueryExpr | None = None
