from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Callable, TypeAlias, TypeVar, cast
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    Select,
    Uuid,
    and_,
    asc,
    desc,
    not_,
    or_,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import ColumnElement, literal
from sqlalchemy.sql.sqltypes import Boolean
from sqlalchemy.sql.type_api import TypeEngine
from ucsschool_objects.core.domain.errors import (
    EmptyAndClause,
    EmptyOrClause,
    InvalidInFilter,
    InvalidJsonFilter,
    InvalidPatternFilter,
    InvalidRangeFilter,
    InvalidUuidFilter,
    UnsupportedFilterField,
    UnsupportedFilterOperator,
    UnsupportedNestedField,
    UnsupportedSortField,
)
from ucsschool_objects.core.domain.query import (
    And,
    Filter,
    FilterInValue,
    FilterValue,
    Not,
    Operator,
    Or,
    SearchQuery,
    SortSpec,
)

if TYPE_CHECKING:  # pragma: no cover
    from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import JoinSpec

RANGE_CAPABLE_TYPES = (Date, DateTime, Float, Integer, Numeric)
RANGE_OPERATORS = frozenset({Operator.GT, Operator.GTE, Operator.LT, Operator.LTE})
SelectT = TypeVar("SelectT", bound=tuple[object, ...])
FieldColumn: TypeAlias = InstrumentedAttribute[object] | ColumnElement[object]
FilterExpression: TypeAlias = ColumnElement[bool]
FilterExpressionBuilder: TypeAlias = Callable[[FieldColumn, FilterValue], FilterExpression]


def _collect_sort_fields(expr: Sequence[SortSpec]) -> set[str]:
    return {spec.field for spec in expr if "." in spec.field}


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

    applied_join = False

    for join_name in required_joins:
        if join_name not in registry:
            continue

        spec = registry[join_name]
        isouter = spec.join_type == "left_outer"

        # Apply each model in the join path
        for join_model in spec.join_path:
            stmt = stmt.join(join_model, isouter=isouter)
            applied_join = True

    # Apply DISTINCT when at least one nested join was applied.
    if applied_join:
        stmt = stmt.distinct()

    return stmt


def _get_column_type(column: FieldColumn) -> TypeEngine[object]:
    return cast(TypeEngine[object], column.type)


def _supports_range_filters(column: FieldColumn) -> bool:
    return isinstance(_get_column_type(column), RANGE_CAPABLE_TYPES)


class _JsonArrayContains(ColumnElement[bool]):
    """Membership test for a value inside a JSON column's key.

    True when the key holds an array containing the value, or a scalar equal
    to it — both backends agree on these semantics: PostgreSQL's
    ``jsonb_exists`` checks array elements and string equality, SQLite's
    ``json_each`` iterates array elements and yields a single row for
    scalars. There is no portable single spelling, hence the per-dialect
    compilation below.
    """

    inherit_cache = False
    type = Boolean()

    def __init__(self, json_column: FieldColumn, json_key: str, value: str) -> None:
        super().__init__()
        self.json_column = json_column
        self.key_param = literal(json_key)
        escaped_key = json_key.replace('"', '\\"')
        self.path_param = literal(f'$."{escaped_key}"')
        self.value_param = literal(value)


@compiles(_JsonArrayContains)
def _compile_json_array_contains(
    element: _JsonArrayContains, compiler: SQLCompiler, **kw: object
) -> str:
    raise NotImplementedError(
        f"JSON array membership is not implemented for dialect {compiler.dialect.name!r}."
    )


@compiles(_JsonArrayContains, "sqlite")
def _compile_json_array_contains_sqlite(
    element: _JsonArrayContains, compiler: SQLCompiler, **kw: object
) -> str:
    column = compiler.process(cast("ColumnElement[object]", element.json_column), **kw)
    path = compiler.process(element.path_param, **kw)
    value = compiler.process(element.value_param, **kw)
    # Not injectable: column is a compiler-emitted column reference, path and
    # value are bind-parameter placeholders.
    return (
        f"EXISTS (SELECT 1 FROM json_each({column}, {path})"  # nosec B608
        f" WHERE json_each.value = {value})"
    )


@compiles(_JsonArrayContains, "postgresql")
def _compile_json_array_contains_postgresql(
    element: _JsonArrayContains, compiler: SQLCompiler, **kw: object
) -> str:
    # Function form of the jsonb ``?`` operator — avoids paramstyle clashes.
    column = compiler.process(cast("ColumnElement[object]", element.json_column), **kw)
    key = compiler.process(element.key_param, **kw)
    value = compiler.process(element.value_param, **kw)
    return f"jsonb_exists(CAST({column} -> {key} AS JSONB), {value})"


def _build_json_contains_expression(
    filter_expr: Filter,
    json_field_map: Mapping[str, FieldColumn] | None,
) -> FilterExpression:
    root, sep, json_key = filter_expr.field.partition(".")
    json_column = json_field_map.get(root) if (sep and json_field_map) else None
    if json_column is None:
        raise UnsupportedFilterOperator(filter_expr.field, filter_expr.op)
    if not isinstance(filter_expr.value, str):
        raise InvalidJsonFilter(filter_expr.field, filter_expr.value)
    return _JsonArrayContains(json_column, json_key, filter_expr.value)


def _json_extracted_column(
    json_column: FieldColumn,
    json_key: str,
    filter_expr: Filter,
) -> FieldColumn:
    """A typed extraction of one key from a JSON column.

    The extraction type follows the filter value's type, so comparisons are
    portable across backends (``->>`` on PostgreSQL, ``JSON_EXTRACT`` on
    SQLite) and downstream operator handling works on the returned element
    like on a real column. Only scalar values are supported — matching
    inside JSON arrays has no portable spelling.
    """
    element = cast("ColumnElement[object]", json_column)[json_key]
    value = filter_expr.value
    # bool first: bool is a subclass of int.
    if isinstance(value, bool):
        return cast("ColumnElement[object]", element.as_boolean())
    if isinstance(value, int):
        return cast("ColumnElement[object]", element.as_integer())
    if isinstance(value, float):
        return cast("ColumnElement[object]", element.as_float())
    if isinstance(value, str):
        return cast("ColumnElement[object]", element.as_string())
    raise InvalidJsonFilter(filter_expr.field, value)


def _get_filter_column(
    filter_expr: Filter,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
    json_field_map: Mapping[str, FieldColumn] | None = None,
) -> FieldColumn:
    """Resolve a filter field to its column, with nested field support.

    Args:
        filter_expr: The filter expression containing the field name.
        field_map: Mapping of field names to columns.
        registry: Optional registry for validating nested fields.
        json_field_map: Optional mapping of JSON column roots; a field like
            ``udm_properties.title`` resolves to a typed extraction of the
            ``title`` key from the mapped JSON column.

    Returns:
        The resolved column.

    Raises:
        UnsupportedFilterField: If the field is not in field_map.
        UnsupportedNestedField: If a nested field references an unknown
            relation or unsupported field.
        InvalidJsonFilter: If a JSON field filter carries a non-scalar value.
    """
    # Fast path: scalar field in map
    if filter_expr.field in field_map:
        return field_map[filter_expr.field]

    # JSON field: extract the key from the mapped JSON column
    if "." in filter_expr.field and json_field_map:
        root, _, json_key = filter_expr.field.partition(".")
        json_column = json_field_map.get(root)
        if json_column is not None:
            return _json_extracted_column(json_column, json_key, filter_expr)

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

        column = field_map.get(filter_expr.field)
        if column is not None:
            return column

        raise UnsupportedNestedField(
            nested_field=filter_expr.field,
            reason=f"Field '{field_part}' is not mapped for relation '{root}'",
            supported_fields=sorted(spec.exposed_fields),
        )

    raise UnsupportedFilterField(filter_expr.field)


def _validate_filter_value(filter_expr: Filter, column: FieldColumn) -> None:
    if filter_expr.op is Operator.IN:
        values = filter_expr.value
        if not isinstance(values, Iterable) or isinstance(values, str):
            raise InvalidInFilter(filter_expr.field, values)
        return

    if filter_expr.op in {Operator.MATCHES, Operator.MATCHES_CI} and not isinstance(
        filter_expr.value, str
    ):
        raise InvalidPatternFilter(filter_expr.field, filter_expr.value)

    if filter_expr.op in RANGE_OPERATORS and (
        filter_expr.value is None or not _supports_range_filters(column)
    ):
        raise InvalidRangeFilter(filter_expr.field, filter_expr.op, filter_expr.value)


_UUID_COERCED_OPERATORS = frozenset({Operator.EQ, Operator.NE, Operator.IN})


def _coerce_uuid(field: str, value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidUuidFilter(field, value) from exc


def _coerce_filter_value(filter_expr: Filter, column: FieldColumn) -> FilterValue:
    """Coerce string values for UUID columns to UUID objects.

    Drivers differ here: psycopg accepts strings for uuid columns, SQLite's
    Uuid type does not. Coercing makes public_id filters backend-agnostic.
    """
    if filter_expr.op not in _UUID_COERCED_OPERATORS or not isinstance(_get_column_type(column), Uuid):
        return filter_expr.value
    if filter_expr.op is Operator.IN:
        values = cast(FilterInValue, filter_expr.value)
        return cast(FilterValue, tuple(_coerce_uuid(filter_expr.field, value) for value in values))
    return cast(FilterValue, _coerce_uuid(filter_expr.field, filter_expr.value))


def _glob_to_sql_pattern(user_glob: str, escape_char: str = "\\") -> str:
    escaped = user_glob.replace(escape_char, escape_char + escape_char)
    escaped = escaped.replace("%", escape_char + "%")
    escaped = escaped.replace("_", escape_char + "_")
    return escaped.replace("*", "%")


FILTER_OPERATOR_BUILDERS: dict[Operator, FilterExpressionBuilder] = {
    Operator.EQ: lambda column, value: column == value,
    Operator.NE: lambda column, value: column != value,
    Operator.IN: lambda column, value: column.in_(tuple(cast(FilterInValue, value))),
    Operator.MATCHES: lambda column, value: column.like(
        _glob_to_sql_pattern(cast(str, value)), escape="\\"
    ),
    Operator.MATCHES_CI: lambda column, value: column.ilike(
        _glob_to_sql_pattern(cast(str, value)), escape="\\"
    ),
    Operator.GT: lambda column, value: column > value,
    Operator.GTE: lambda column, value: column >= value,
    Operator.LT: lambda column, value: column < value,
    Operator.LTE: lambda column, value: column <= value,
}


def _build_filter_expression(
    filter_expr: Filter,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
    json_field_map: Mapping[str, FieldColumn] | None = None,
) -> FilterExpression:
    if filter_expr.op is Operator.CONTAINS:
        return _build_json_contains_expression(filter_expr, json_field_map)
    column = _get_filter_column(filter_expr, field_map, registry, json_field_map)
    _validate_filter_value(filter_expr, column)

    builder = FILTER_OPERATOR_BUILDERS.get(filter_expr.op)
    if builder is None:
        raise UnsupportedFilterOperator(filter_expr.field, filter_expr.op)
    return builder(column, _coerce_filter_value(filter_expr, column))


def build_expression(
    query_expr: Filter | And | Or | Not,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
    json_field_map: Mapping[str, FieldColumn] | None = None,
) -> FilterExpression:
    if isinstance(query_expr, Filter):
        return _build_filter_expression(query_expr, field_map, registry, json_field_map)

    if isinstance(query_expr, And):
        if not query_expr.clauses:
            raise EmptyAndClause()
        return and_(
            *(
                build_expression(clause, field_map, registry, json_field_map)
                for clause in query_expr.clauses
            )
        )

    if isinstance(query_expr, Or):
        if not query_expr.clauses:
            raise EmptyOrClause()
        return or_(
            *(
                build_expression(clause, field_map, registry, json_field_map)
                for clause in query_expr.clauses
            )
        )

    return not_(build_expression(query_expr.clause, field_map, registry, json_field_map))


def apply_search_query(
    stmt: Select[SelectT],
    query: SearchQuery | None,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
    json_field_map: Mapping[str, FieldColumn] | None = None,
) -> Select[SelectT]:
    if query is None or query.where is None:
        return stmt

    # Apply nested joins if needed
    required_joins = _get_required_joins(query.where, registry)
    stmt = apply_nested_joins(stmt, required_joins, registry)

    # Build and apply filter expression
    return stmt.where(build_expression(query.where, field_map, registry, json_field_map))


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
