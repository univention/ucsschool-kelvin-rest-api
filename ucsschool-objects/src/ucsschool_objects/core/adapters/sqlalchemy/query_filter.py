# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Callable, TypeAlias, TypeVarTuple, cast
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    Select,
    String,
    Uuid,
    and_,
    asc,
    desc,
    exists,
    func,
    not_,
    or_,
    select,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import aliased, join as orm_join
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import ColumnElement, literal
from sqlalchemy.sql.sqltypes import Boolean
from sqlalchemy.sql.type_api import TypeEngine

from ucsschool_objects.core.adapters.sqlalchemy.query_schema import (
    ComputedField,
    FieldColumn,
    JoinSpec,
    ModelClass,
)
from ucsschool_objects.core.domain.errors import (
    EmptyAndClause,
    EmptyOrClause,
    InvalidAnyClause,
    InvalidInFilter,
    InvalidJsonFilter,
    InvalidPatternFilter,
    InvalidRangeFilter,
    InvalidSearchAfter,
    InvalidUuidFilter,
    UnsupportedFilterField,
    UnsupportedFilterOperator,
    UnsupportedNestedField,
    UnsupportedQueryExpression,
    UnsupportedSortField,
)
from ucsschool_objects.core.domain.query import (
    And,
    Any,
    Filter,
    FilterInValue,
    FilterScalarValue,
    FilterValue,
    Not,
    Operator,
    Or,
    QueryExpr,
    SearchQuery,
    SortSpec,
)

RANGE_CAPABLE_TYPES = (Date, DateTime, Float, Integer, Numeric)
RANGE_OPERATORS = frozenset({Operator.GT, Operator.GTE, Operator.LT, Operator.LTE})
SelectTs = TypeVarTuple("SelectTs")
FilterExpression: TypeAlias = ColumnElement[bool]
FilterExpressionBuilder: TypeAlias = Callable[[FieldColumn, FilterValue], FilterExpression]


def _children(expr: QueryExpr) -> tuple[QueryExpr, ...]:
    if isinstance(expr, (And, Or)):
        return expr.clauses
    if isinstance(expr, Not):
        return (expr.clause,)
    raise UnsupportedQueryExpression(expr)


def _query_fields(expr: QueryExpr, *, inside_any: bool = False) -> set[str]:
    fields: set[str] = set()
    stack: list[QueryExpr] = [expr]

    while stack:
        query_expr = stack.pop()
        if isinstance(query_expr, Filter):
            fields.add(query_expr.field)
        elif not isinstance(query_expr, Any):
            stack.extend(_children(query_expr))
        elif inside_any:
            raise InvalidAnyClause("Any cannot be nested in Any")

    return fields


def _nested_roots(fields: Iterable[str], registry: Mapping[str, JoinSpec]) -> set[str]:
    roots: set[str] = set()
    for field in fields:
        root, sep, _ = field.partition(".")
        if sep and root in registry:
            roots.add(root)
    return roots


def apply_nested_joins(
    stmt: Select[*SelectTs],
    model: ModelClass,
    required_joins: set[str],
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
) -> tuple[Select[*SelectTs], dict[str, FieldColumn]]:
    """Join each required relation through its own aliases.

    Relations that share a table (e.g. ``schools`` and ``roles`` both pass
    ``school_membership``) are thereby matched independently of each other.

    Args:
        stmt: The base SELECT statement.
        model: The model selected by ``stmt``; every join path starts there.
        required_joins: Set of relationship names that need to be joined (e.g., {'groups', 'roles'}).
        field_map: Mapping of field names to columns.
        registry: The JoinSpec registry mapping relationship names to join specifications.

    Returns:
        The joined statement, DISTINCT if a to-many relation was joined, and the
        nested fields of ``field_map`` resolved against the aliases.
    """
    if registry is None or not required_joins:
        return stmt, {}

    nested_columns: dict[str, FieldColumn] = {}
    joined_to_many = False

    for join_name in sorted(required_joins):
        if join_name not in registry:
            continue

        spec = registry[join_name]
        isouter = spec.join_type == "left_outer"

        left = model
        for join_model in spec.join_path:
            right = aliased(join_model)
            stmt = stmt.join_from(left, right, isouter=isouter)
            left = right

        nested_columns.update(_resolve_nested_fields(field_map, join_name, left))
        joined_to_many = joined_to_many or spec.to_many

    if joined_to_many:
        stmt = stmt.distinct()

    return stmt, nested_columns


def _resolve_nested_fields(
    field_map: Mapping[str, FieldColumn],
    join_name: str,
    target: ModelClass,
) -> dict[str, FieldColumn]:
    prefix = f"{join_name}."
    return {
        field: cast(FieldColumn, getattr(target, field.removeprefix(prefix)))
        for field in field_map
        if field.startswith(prefix)
    }


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
        f"EXISTS (SELECT 1 FROM json_each({column}, {path})"  # noqa: S608
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
    if filter_expr.op in {Operator.IN, Operator.IN_CI}:
        values = filter_expr.value
        if not isinstance(values, Iterable) or isinstance(values, str):
            raise InvalidInFilter(filter_expr.field, values)
        if filter_expr.op is Operator.IN_CI and not isinstance(_get_column_type(column), String):
            raise InvalidInFilter(
                filter_expr.field,
                values,
                reason="requires a string field when matching case-insensitively",
            )
        if filter_expr.op is Operator.IN_CI and not all(isinstance(value, str) for value in values):
            raise InvalidInFilter(
                filter_expr.field,
                values,
                reason="requires string values when matching case-insensitively",
            )
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
    # Both sides are folded by the database, so that one engine decides what
    # case-insensitive means; Python's str.lower() and SQL lower() disagree on
    # non-ASCII text.
    Operator.IN_CI: lambda column, value: func.lower(column).in_(
        tuple(func.lower(literal(cast(str, item))) for item in cast(FilterInValue, value))
    ),
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
    if (
        filter_expr.op in {Operator.IN, Operator.IN_CI}
        and isinstance(filter_expr.value, Iterable)
        and not isinstance(filter_expr.value, Collection)
    ):
        # A one-shot iterable would be used up by validation before the
        # expression is built from it.
        filter_expr = replace(filter_expr, value=tuple(filter_expr.value))
    column = _get_filter_column(filter_expr, field_map, registry, json_field_map)
    _validate_filter_value(filter_expr, column)

    builder = FILTER_OPERATOR_BUILDERS.get(filter_expr.op)
    if builder is None:
        raise UnsupportedFilterOperator(filter_expr.field, filter_expr.op)
    return builder(column, _coerce_filter_value(filter_expr, column))


@dataclass(frozen=True)
class AnyContext:
    model: ModelClass
    computed_fields: Mapping[str, ComputedField]


def _build_any_expression(
    any_expr: Any,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None,
    json_field_map: Mapping[str, FieldColumn] | None,
    any_context: AnyContext | None,
) -> FilterExpression:
    """An EXISTS over the related rows of ``any_context.model``, correlated on it only.

    Join paths share their common prefix, so all fields of the clause are
    checked on one combined related row.
    """
    if any_context is None:
        raise InvalidAnyClause("not supported for this object type")
    any_model = any_context.model
    registry = registry or {}
    fields = _query_fields(any_expr.clause, inside_any=True)
    computed = {
        field: any_context.computed_fields[field]
        for field in fields & any_context.computed_fields.keys()
    }
    roots = _nested_roots(fields, registry)
    roots.update(root for computed_field in computed.values() for root in computed_field.roots)
    unnested = sorted(
        field for field in fields - computed.keys() if field.partition(".")[0] not in roots
    )
    if unnested:
        raise InvalidAnyClause(f"fields must be nested in one of {sorted(registry)}; got {unnested}")

    subquery = select(literal(1))
    aliases: dict[tuple[ModelClass, ...], ModelClass] = {}
    nested_columns: dict[str, FieldColumn] = {}
    targets: dict[str, ModelClass] = {}
    for root in sorted(roots):
        left = any_model
        path: tuple[ModelClass, ...] = ()
        for join_model in registry[root].join_path:
            path = (*path, join_model)
            right = aliases.get(path)
            if right is None:
                right = aliases[path] = aliased(join_model)
                if left is any_model:
                    correlation = cast("ColumnElement[bool]", orm_join(any_model, right).onclause)
                    subquery = subquery.select_from(right).where(correlation)
                else:
                    subquery = subquery.join_from(left, right)
            left = right
        nested_columns.update(_resolve_nested_fields(field_map, root, left))
        targets[root] = left
    nested_columns.update(
        {field: computed_field.build(targets) for field, computed_field in computed.items()}
    )

    condition = build_expression(
        any_expr.clause, {**field_map, **nested_columns}, registry, json_field_map
    )
    return exists(subquery.where(condition).correlate(any_model))


def build_expression(
    query_expr: QueryExpr,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
    json_field_map: Mapping[str, FieldColumn] | None = None,
    *,
    any_context: AnyContext | None = None,
) -> FilterExpression:
    if isinstance(query_expr, Filter):
        return _build_filter_expression(query_expr, field_map, registry, json_field_map)

    if isinstance(query_expr, And):
        if not query_expr.clauses:
            raise EmptyAndClause()
        return and_(
            *(
                build_expression(clause, field_map, registry, json_field_map, any_context=any_context)
                for clause in query_expr.clauses
            )
        )

    if isinstance(query_expr, Or):
        if not query_expr.clauses:
            raise EmptyOrClause()
        return or_(
            *(
                build_expression(clause, field_map, registry, json_field_map, any_context=any_context)
                for clause in query_expr.clauses
            )
        )

    if isinstance(query_expr, Not):
        return not_(
            build_expression(
                query_expr.clause, field_map, registry, json_field_map, any_context=any_context
            )
        )

    if isinstance(query_expr, Any):  # pyright: ignore[reportUnnecessaryIsInstance]
        return _build_any_expression(query_expr, field_map, registry, json_field_map, any_context)

    raise UnsupportedQueryExpression(query_expr)  # pyright: ignore[reportUnreachable]


def apply_search_query(
    stmt: Select[*SelectTs],
    query: SearchQuery | None,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None,
    json_field_map: Mapping[str, FieldColumn] | None = None,
    *,
    model: ModelClass,
    allow_any: bool = False,
    computed_fields: Mapping[str, ComputedField] | None = None,
) -> Select[*SelectTs]:
    if query is None or query.where is None:
        return stmt

    required_joins = _nested_roots(_query_fields(query.where), registry or {})
    stmt, nested_columns = apply_nested_joins(stmt, model, required_joins, field_map, registry)

    return stmt.where(
        build_expression(
            query.where,
            {**field_map, **nested_columns},
            registry,
            json_field_map,
            any_context=AnyContext(model, computed_fields or {}) if allow_any else None,
        )
    )


def _search_after_condition(
    specs: tuple[SortSpec, ...],
    search_after: tuple[FilterScalarValue, ...],
    field_map: Mapping[str, FieldColumn],
) -> ColumnElement[bool]:
    """Rows sorting strictly after ``search_after`` in the order of ``specs``.

    Spelled out per position instead of as a row-value comparison, so that
    every sort field can have its own direction:
    ``a > x OR (a = x AND b > y) OR ...``.
    """
    if len(search_after) != len(specs) or any(value is None for value in search_after):
        raise InvalidSearchAfter(search_after, tuple(spec.field for spec in specs))
    alternatives: list[ColumnElement[bool]] = []
    for position, spec in enumerate(specs):
        column = field_map[spec.field]
        value = search_after[position]
        equal_before = [
            field_map[earlier.field] == search_after[index]
            for index, earlier in enumerate(specs[:position])
        ]
        beyond = column > value if spec.ascending else column < value
        alternatives.append(and_(*equal_before, beyond))
    return or_(*alternatives)


def apply_sort(
    stmt: Select[*SelectTs],
    sort_by: Sequence[SortSpec],
    field_map: Mapping[str, FieldColumn],
    *,
    model: ModelClass,
    default_field: str = "public_id",
    registry: dict[str, JoinSpec] | None = None,
    search_after: Sequence[FilterScalarValue] | None = None,
) -> Select[*SelectTs]:
    specs = tuple(sort_by) or (SortSpec(default_field),)

    required_joins = _nested_roots((spec.field for spec in specs), registry or {})
    for spec in specs:
        root, sep, _ = spec.field.partition(".")
        if sep and root in required_joins and cast("dict[str, JoinSpec]", registry)[root].to_many:
            raise UnsupportedSortField(spec.field)
    stmt, nested_columns = apply_nested_joins(stmt, model, required_joins, field_map, registry)
    field_map = {**field_map, **nested_columns}

    ordering = specs
    if default_field in field_map and all(spec.field != default_field for spec in specs):
        ordering = (*specs, SortSpec(default_field))

    for spec in ordering:
        if spec.field not in field_map:
            raise UnsupportedSortField(spec.field)
        column = field_map[spec.field]
        stmt = stmt.order_by(asc(column) if spec.ascending else desc(column))
    if search_after is not None:
        # Keyed on the requested fields only: the appended default field breaks
        # ties in the order, but is not part of the position the caller gave.
        stmt = stmt.where(_search_after_condition(specs, tuple(search_after), field_map))
    return stmt
