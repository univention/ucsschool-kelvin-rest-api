from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Callable, TypeAlias, TypeVar, cast

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
    UnsupportedNestedField,
    UnsupportedSortField,
)

if TYPE_CHECKING:  # pragma: no cover
    from ucsschool_objects.core.adapters.sqlalchemy.managers import JoinSpec

RANGE_CAPABLE_TYPES = (Date, DateTime, Float, Integer, Numeric)
RANGE_OPERATORS = frozenset({Operator.GT, Operator.GTE, Operator.LT, Operator.LTE})
SelectT = TypeVar("SelectT", bound=tuple[object, ...])
FieldColumn: TypeAlias = InstrumentedAttribute[object] | ColumnElement[object]
FilterExpression: TypeAlias = ColumnElement[bool]
FilterExpressionBuilder: TypeAlias = Callable[[FieldColumn, FilterValue], FilterExpression]


def _collect_sort_fields(expr: Sequence[SortSpec]) -> set[str]:
    return {spec.field for spec in expr if isinstance(spec, SortSpec) and "." in spec.field}


def _collect_query_fields(expr: Filter | And | Or | Not) -> set[str]:
    fields: set[str] = set()
    stack: list[Filter | And | Or | Not] = [expr]

    while stack:
        query_expr = stack.pop()
        if isinstance(query_expr, Filter):
            fields.add(query_expr.field)
        elif isinstance(query_expr, (And, Or)):
            stack.extend(query_expr.clauses)
        else:  # Not
            stack.append(query_expr.clause)

    return fields


def _extract_registered_nested_roots(fields: set[str], registry: dict[str, JoinSpec]) -> set[str]:
    roots: set[str] = set()
    for field in fields:
        root, sep, _ = field.partition(".")
        if sep and root in registry:
            roots.add(root)
    return roots


def _get_required_joins(
    expr: Filter | And | Or | Not | Sequence[SortSpec] | None,
    registry: dict[str, JoinSpec] | None = None,
) -> set[str]:
    """Extract set of required join names (e.g., {'groups', 'schools'}) from a query
    expression or sort specs.

    A join is required if any nested field (contains '.') references a root relationship
    in the registry.
    """
    if registry is None:
        return set()

    if isinstance(expr, Sequence) and not isinstance(expr, str):
        return _extract_registered_nested_roots(
            _collect_sort_fields(expr),
            registry,
        )

    if isinstance(expr, (Filter, And, Or, Not)):
        return _extract_registered_nested_roots(
            _collect_query_fields(expr),
            registry,
        )

    return set()


def apply_nested_joins(
    stmt: Select[SelectT],
    required_joins: set[str],
    registry: dict[str, JoinSpec] | None = None,
) -> Select[SelectT]:
    """Apply necessary joins for nested relationships and return DISTINCT-wrapped statement.

    Args:
        stmt: The base SELECT statement.
        required_joins: Set of relationship names that need to be joined (e.g., {'groups', 'roles'}).
        registry: The JoinSpec registry mapping relationship names to join specifications.

    Returns:
        Modified statement with joins applied and DISTINCT if N:M relationships are present.
    """
    if registry is None or not required_joins:
        return stmt

    for join_name in required_joins:
        if join_name not in registry:
            continue

        spec = registry[join_name]
        isouter = spec.join_type == "left_outer"

        # Apply each model in the join path
        for join_model in spec.join_path:
            stmt = stmt.join(join_model, isouter=isouter)

    # Apply DISTINCT if multiple joins (prevents duplicates from N:M relationships)
    if len(required_joins) > 1:
        stmt = stmt.distinct()

    return stmt


def _get_column_type(column: FieldColumn) -> TypeEngine[object] | None:
    if isinstance(column, InstrumentedAttribute):
        return cast(TypeEngine[object], column.property.columns[0].type)
    # Keep fallback for expression-backed field maps (ColumnElement), e.g. computed
    # search/sort fields that may be introduced by future manager implementations.
    return cast(TypeEngine[object] | None, getattr(column, "type", None))


def _supports_range_filters(column: FieldColumn) -> bool:
    column_type = _get_column_type(column)
    return column_type is not None and isinstance(column_type, RANGE_CAPABLE_TYPES)


def _get_filter_column(
    filter_expr: Filter,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
) -> FieldColumn:
    """Resolve a filter field to its column, with nested field support.

    Args:
        filter_expr: The filter expression containing the field name.
        field_map: Mapping of field names to columns.
        registry: Optional registry for validating nested fields.

    Returns:
        The resolved column.

    Raises:
        UnsupportedFilterField: If the field is not in field_map.
        UnsupportedNestedField: If a nested field references an unknown
            relation or unsupported field.
    """
    # Fast path: scalar field in map
    if filter_expr.field in field_map:
        return field_map[filter_expr.field]

    # Nested field: validate against registry
    if "." in filter_expr.field and registry:
        root, _, field_part = filter_expr.field.partition(".")

        if root not in registry:
            raise UnsupportedNestedField(
                nested_field=filter_expr.field,
                root_relation=root,
                allowed_relations=list(registry.keys()),
            )

        spec = registry[root]
        if field_part not in spec.exposed_fields:
            raise UnsupportedNestedField(
                nested_field=filter_expr.field,
                reason=f"Field '{field_part}' not supported on relation '{root}'",
                supported_fields=sorted(spec.exposed_fields),
            )

        # Return from field_map if pre-populated, else resolve directly from
        # validated model attribute.
        return field_map.get(filter_expr.field, getattr(spec.target_model, field_part))

    raise UnsupportedFilterField(filter_expr.field)


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
    filter_expr: Filter,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
) -> FilterExpression:
    column = _get_filter_column(filter_expr, field_map, registry)
    _validate_filter_value(filter_expr, column)

    builder = FILTER_OPERATOR_BUILDERS.get(filter_expr.op)
    if builder is None:
        raise UnsupportedFilterOperator(filter_expr.field, filter_expr.op)
    return builder(column, filter_expr.value)


def build_expression(
    query_expr: Filter | And | Or | Not,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
) -> FilterExpression:
    if isinstance(query_expr, Filter):
        return _build_filter_expression(query_expr, field_map, registry)

    if isinstance(query_expr, And):
        if not query_expr.clauses:
            raise EmptyAndClause()
        return and_(*(build_expression(clause, field_map, registry) for clause in query_expr.clauses))

    if isinstance(query_expr, Or):
        if not query_expr.clauses:
            raise EmptyOrClause()
        return or_(*(build_expression(clause, field_map, registry) for clause in query_expr.clauses))

    return not_(build_expression(query_expr.clause, field_map, registry))


def apply_search_query(
    stmt: Select[SelectT],
    query: SearchQuery | None,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
) -> Select[SelectT]:
    if query is None or query.where is None:
        return stmt

    # Apply nested joins if needed
    required_joins = _get_required_joins(query.where, registry)
    stmt = apply_nested_joins(stmt, required_joins, registry)

    # Build and apply filter expression
    return stmt.where(build_expression(query.where, field_map, registry))


def apply_sort(
    stmt: Select[SelectT],
    sort_by: Sequence[SortSpec],
    field_map: Mapping[str, FieldColumn],
    *,
    default_field: str = "public_id",
    registry: dict[str, JoinSpec] | None = None,
) -> Select[SelectT]:
    specs = tuple(sort_by) or (SortSpec(default_field),)

    # Apply nested joins if needed
    required_joins = _get_required_joins(specs, registry)
    stmt = apply_nested_joins(stmt, required_joins, registry)

    if default_field in field_map and all(spec.field != default_field for spec in specs):
        specs = (*specs, SortSpec(default_field))

    for spec in specs:
        if spec.field not in field_map:
            raise UnsupportedSortField(spec.field)
        column = field_map[spec.field]
        stmt = stmt.order_by(asc(column) if spec.ascending else desc(column))
    return stmt
