"""Tests for make_wildcard_filter factory function.

Verifies the domain stores raw glob intent and leaves backend translation to
the adapter.
"""

import pytest
from ucsschool_objects import Filter, Operator, make_wildcard_filter


@pytest.mark.parametrize(
    ("field", "user_value", "case_insensitive", "expected_operator"),
    [
        pytest.param("name", "test*", False, Operator.MATCHES, id="case-sensitive"),
        pytest.param("name", "test*", True, Operator.MATCHES_CI, id="case-insensitive"),
        pytest.param("name", "50%_test*", False, Operator.MATCHES, id="raw-metacharacters"),
        pytest.param("school.name", "", False, Operator.MATCHES, id="empty-pattern"),
    ],
)
def test_make_wildcard_filter_valid_cases(
    field: str,
    user_value: str,
    case_insensitive: bool,
    expected_operator: Operator,
) -> None:
    result = make_wildcard_filter(field, user_value, case_insensitive=case_insensitive)

    assert isinstance(result, Filter)
    assert result.field == field
    assert result.op == expected_operator
    assert result.value == user_value


@pytest.mark.parametrize(
    ("field", "user_value", "expected_exception", "message"),
    [
        pytest.param("name", 123, TypeError, "user_value must be str, got int", id="user-int"),
        pytest.param("name", None, TypeError, "user_value must be str, got NoneType", id="user-none"),
        pytest.param("name", b"test", TypeError, "user_value must be str, got bytes", id="user-bytes"),
        pytest.param("", "test", ValueError, "field must be a non-empty string", id="field-empty"),
        pytest.param(123, "test", ValueError, "field must be a non-empty string", id="field-int"),
        pytest.param(None, "test", ValueError, "field must be a non-empty string", id="field-none"),
    ],
)
def test_make_wildcard_filter_invalid_cases(
    field: object,
    user_value: object,
    expected_exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(expected_exception, match=message):
        make_wildcard_filter(field, user_value)  # type: ignore[arg-type]
