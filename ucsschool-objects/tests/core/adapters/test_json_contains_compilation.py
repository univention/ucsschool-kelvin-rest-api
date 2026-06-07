from __future__ import annotations

import pytest
from sqlalchemy.dialects import mysql, postgresql, sqlite
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import _JsonArrayContains
from ucsschool_objects.database_models import User as UserModel


def _compile(dialect: object) -> str:
    expression = _JsonArrayContains(UserModel.udm_properties, "e-mail", "a@example.com")
    return str(expression.compile(dialect=dialect))  # type: ignore[arg-type]


def test_json_array_contains_compiles_on_sqlite() -> None:
    sql = _compile(sqlite.dialect())
    assert "json_each" in sql
    assert "EXISTS" in sql


def test_json_array_contains_compiles_on_postgresql() -> None:
    sql = _compile(postgresql.dialect())  # type: ignore[no-untyped-call]
    assert "jsonb_exists" in sql
    assert "AS JSONB" in sql


def test_json_array_contains_rejects_unsupported_dialects() -> None:
    with pytest.raises(NotImplementedError, match="not implemented for dialect 'mysql'"):
        _compile(mysql.dialect())
