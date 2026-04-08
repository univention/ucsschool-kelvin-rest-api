from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Operator(StrEnum):
    EQ = "eq"
    IN = "in"
    LIKE = "like"


@dataclass(frozen=True, slots=True)
class Filter:
    field: str
    op: Operator
    value: object


@dataclass(frozen=True, slots=True)
class And:
    clauses: tuple[QueryExpr, ...]


@dataclass(frozen=True, slots=True)
class Or:
    clauses: tuple[QueryExpr, ...]


QueryExpr = Filter | And | Or


@dataclass(frozen=True, slots=True)
class SearchQuery:
    where: QueryExpr | None = None


@dataclass(frozen=True, slots=True)
class SortSpec:
    field: str
    ascending: bool = True
