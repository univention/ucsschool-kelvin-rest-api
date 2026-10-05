# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import pytest
from pydantic import TypeAdapter, ValidationError

from ucsschool.kelvin.schema import HttpUrl

http_url_adapter: TypeAdapter[str] = TypeAdapter(HttpUrl)


def test_http_url_keeps_the_string_as_sent() -> None:
    assert http_url_adapter.validate_python("https://Example.com/a b") == "https://Example.com/a b"


@pytest.mark.parametrize(
    "url", ["https://example.com/x ", " https://example.com/x", "https://example.com/x\n"]
)
def test_http_url_rejects_surrounding_whitespace(url: str) -> None:
    with pytest.raises(ValidationError, match="whitespace"):
        http_url_adapter.validate_python(url)


def test_http_url_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        http_url_adapter.validate_python("not a url")
