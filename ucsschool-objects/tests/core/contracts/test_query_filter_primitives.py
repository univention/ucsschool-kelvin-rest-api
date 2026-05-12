from __future__ import annotations

from typing import cast

from sqlalchemy import Integer, func
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import FieldColumn, build_expression
from ucsschool_objects.core.domain import Filter, Operator
from ucsschool_objects.database_models import User as UserModel


def test_build_expression_supports_column_element_range_types() -> None:
    """Ensure ColumnElement-based field maps remain supported for future computed fields.

    Current managers mostly map filters to InstrumentedAttribute instances. This test
    intentionally uses a typed SQL expression derived from a real model column to
    cover the fallback branch in query_filter._get_column_type() so expression-backed
    field maps can be added later without breaking range operator validation.
    """
    field_map: dict[str, FieldColumn] = {
        "name_length": cast("FieldColumn", func.length(UserModel.name, type_=Integer()))
    }

    expression = build_expression(
        Filter(field="name_length", op=Operator.GTE, value=10),
        field_map,
    )

    compiled = str(expression.compile(compile_kwargs={"literal_binds": True}))

    assert "length(" in compiled.lower()
    assert "name" in compiled.lower()
    assert ">= 10" in compiled
