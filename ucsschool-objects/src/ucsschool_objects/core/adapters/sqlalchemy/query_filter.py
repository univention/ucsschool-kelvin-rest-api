from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Callable, TypeAlias, TypeVar, cast

from sqlalchemy import Date, DateTime, Float, Integer, Numeric, Select, and_, asc, desc, not_, or_
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.type_api import TypeEngine
from ucsschool_objects.core.domain import (
    And,
    EmptyAndClause,
    EmptyOrClause,
    Filter,
    FilterInValue,
    FilterValue,
    InvalidInFilter,
    InvalidLikeFilter,
    InvalidRangeFilter,
    Not,
    Operator,
    Or,
    SearchQuery,
    SortSpec,
    UnsupportedFilterField,
    UnsupportedFilterOperator,
    UnsupportedSortField,
)

RANGE_CAPABLE_TYPES = (Date, DateTime, Float, Integer, Numeric)
RANGE_OPERATORS = frozenset({Operator.GT, Operator.GTE, Operator.LT, Operator.LTE})
SelectT = TypeVar("SelectT", bound=tuple[object, ...])
FieldColumn: TypeAlias = InstrumentedAttribute[object] | ColumnElement[object]
FilterExpression: TypeAlias = ColumnElement[bool]
FilterExpressionBuilder: TypeAlias = Callable[[FieldColumn, FilterValue], FilterExpression]


def _get_column_type(column: FieldColumn) -> TypeEngine[object] | None:
    if isinstance(column, InstrumentedAttribute):
        return cast(TypeEngine[object], column.property.columns[0].type)
    return cast(TypeEngine[object] | None, getattr(column, "type", None))


def _supports_range_filters(column: FieldColumn) -> bool:
    column_type = _get_column_type(column)
    return column_type is not None and isinstance(column_type, RANGE_CAPABLE_TYPES)


def _get_filter_column(filter_expr: Filter, field_map: Mapping[str, FieldColumn]) -> FieldColumn:
    try:
        return field_map[filter_expr.field]
    except KeyError as exc:
        raise UnsupportedFilterField(filter_expr.field) from exc


def _validate_filter_value(filter_expr: Filter, column: FieldColumn) -> None:
    if filter_expr.op is Operator.IN:
        values = filter_expr.value
        if not isinstance(values, Iterable) or isinstance(values, str):
            raise InvalidInFilter(filter_expr.field, values)
        return

    if filter_expr.op is Operator.LIKE and not isinstance(filter_expr.value, str):
        raise InvalidLikeFilter(filter_expr.field, filter_expr.value)

    if filter_expr.op in RANGE_OPERATORS and (
        filter_expr.value is None or not _supports_range_filters(column)
    ):
        raise InvalidRangeFilter(filter_expr.field, filter_expr.op, filter_expr.value)


FILTER_OPERATOR_BUILDERS: dict[Operator, FilterExpressionBuilder] = {
    Operator.EQ: lambda column, value: column == value,
    Operator.NE: lambda column, value: column != value,
    Operator.IN: lambda column, value: column.in_(tuple(cast(FilterInValue, value))),
    Operator.LIKE: lambda column, value: column.ilike(value),
    Operator.GT: lambda column, value: column > value,
    Operator.GTE: lambda column, value: column >= value,
    Operator.LT: lambda column, value: column < value,
    Operator.LTE: lambda column, value: column <= value,
}


def _build_filter_expression(
    filter_expr: Filter, field_map: Mapping[str, FieldColumn]
) -> FilterExpression:
    column = _get_filter_column(filter_expr, field_map)
    _validate_filter_value(filter_expr, column)

    builder = FILTER_OPERATOR_BUILDERS.get(filter_expr.op)
    if builder is None:
        raise UnsupportedFilterOperator(filter_expr.field, filter_expr.op)
    return builder(column, filter_expr.value)


def build_expression(
    query_expr: Filter | And | Or | Not, field_map: Mapping[str, FieldColumn]
) -> FilterExpression:
    if isinstance(query_expr, Filter):
        return _build_filter_expression(query_expr, field_map)

    if isinstance(query_expr, And):
        if not query_expr.clauses:
            raise EmptyAndClause()
        return and_(*(build_expression(clause, field_map) for clause in query_expr.clauses))

    if isinstance(query_expr, Or):
        if not query_expr.clauses:
            raise EmptyOrClause()
        return or_(*(build_expression(clause, field_map) for clause in query_expr.clauses))

    return not_(build_expression(query_expr.clause, field_map))


def apply_search_query(
    stmt: Select[SelectT],
    query: SearchQuery | None,
    field_map: Mapping[str, FieldColumn],
) -> Select[SelectT]:
    if query is None or query.where is None:
        return stmt
    return stmt.where(build_expression(query.where, field_map))


def apply_sort(
    stmt: Select[SelectT],
    sort_by: Sequence[SortSpec],
    field_map: Mapping[str, FieldColumn],
    *,
    default_field: str = "public_id",
) -> Select[SelectT]:
    specs = tuple(sort_by) or (SortSpec(default_field),)
    if default_field in field_map and all(spec.field != default_field for spec in specs):
        specs = (*specs, SortSpec(default_field))
    for spec in specs:
        if spec.field not in field_map:
            raise UnsupportedSortField(spec.field)
        column = field_map[spec.field]
        stmt = stmt.order_by(asc(column) if spec.ascending else desc(column))
    return stmt
