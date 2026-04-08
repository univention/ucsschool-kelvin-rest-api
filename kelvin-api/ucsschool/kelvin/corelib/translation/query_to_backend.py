from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Select, and_, asc, desc, not_, or_

from ucsschool.kelvin.corelib.domain import (
    And,
    Filter,
    InvalidFilter,
    Not,
    Operator,
    Or,
    SearchQuery,
    SortSpec,
)


def build_expression(query_expr: Filter | And | Or | Not, field_map: dict[str, Any]) -> Any:
    if isinstance(query_expr, Filter):
        try:
            column = field_map[query_expr.field]
        except KeyError as exc:
            raise InvalidFilter(f"Unsupported field: {query_expr.field}") from exc

        if query_expr.op is Operator.EQ:
            return column == query_expr.value
        if query_expr.op is Operator.NE:
            return column != query_expr.value
        if query_expr.op is Operator.IN:
            values = query_expr.value
            if not isinstance(values, Iterable) or isinstance(values, str):
                raise InvalidFilter(
                    f"IN operator requires an iterable value for field '{query_expr.field}'."
                )
            return column.in_(tuple(values))
        if query_expr.op is Operator.LIKE:
            if not isinstance(query_expr.value, str):
                raise InvalidFilter(
                    f"LIKE operator requires a string value for field '{query_expr.field}'."
                )
            return column.ilike(query_expr.value)
        if query_expr.op is Operator.GT:
            return column > query_expr.value
        if query_expr.op is Operator.GTE:
            return column >= query_expr.value
        if query_expr.op is Operator.LT:
            return column < query_expr.value
        if query_expr.op is Operator.LTE:
            return column <= query_expr.value
        raise InvalidFilter(f"Unsupported operator: {query_expr.op}")

    if isinstance(query_expr, And):
        if not query_expr.clauses:
            raise InvalidFilter("AND query requires at least one clause.")
        return and_(*(build_expression(clause, field_map) for clause in query_expr.clauses))

    if isinstance(query_expr, Or):
        if not query_expr.clauses:
            raise InvalidFilter("OR query requires at least one clause.")
        return or_(*(build_expression(clause, field_map) for clause in query_expr.clauses))

    return not_(build_expression(query_expr.clause, field_map))


def apply_search_query(
    stmt: Select[Any],
    query: SearchQuery | None,
    field_map: dict[str, Any],
) -> Select[Any]:
    if query is None or query.where is None:
        return stmt
    return stmt.where(build_expression(query.where, field_map))


def apply_sort(
    stmt: Select[Any],
    sort_by: Sequence[SortSpec],
    field_map: dict[str, Any],
    *,
    default_field: str = "public_id",
) -> Select[Any]:
    specs = sort_by or (SortSpec(default_field),)
    for spec in specs:
        if spec.field not in field_map:
            raise InvalidFilter(f"Unsupported sort field: {spec.field}")
        column = field_map[spec.field]
        stmt = stmt.order_by(asc(column) if spec.ascending else desc(column))
    return stmt
