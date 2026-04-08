import pytest

from ucsschool.kelvin.corelib.domain import InvalidFilter, NotFound, UnsupportedOperation


@pytest.mark.parametrize("exc_cls", [InvalidFilter, NotFound, UnsupportedOperation])
def test_domain_errors_are_exceptions(exc_cls: type[Exception]) -> None:
    with pytest.raises(exc_cls):
        raise exc_cls("boom")
