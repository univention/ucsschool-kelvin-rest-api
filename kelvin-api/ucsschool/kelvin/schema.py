# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared types for the Kelvin API models."""

from typing import Annotated, ClassVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    HttpUrl as _PydanticHttpUrl,
    TypeAdapter,
    WithJsonSchema,
)

_http_url_adapter: TypeAdapter[_PydanticHttpUrl] = TypeAdapter(_PydanticHttpUrl)


def _validate_http_url(value: str) -> str:
    if value != value.strip():
        raise ValueError("URL must not start or end with whitespace.")
    _ = _http_url_adapter.validate_python(value)
    return value


# pydantic 2's HttpUrl is no str and normalizes the URL; the routers work on the string as sent.
HttpUrl = Annotated[
    str,
    AfterValidator(_validate_http_url),
    WithJsonSchema(_http_url_adapter.json_schema()),
]


class KelvinBaseModel(BaseModel):
    """Base class of all models that appear in the Kelvin API's OpenAPI document."""

    # pydantic 1 accepted numbers for string fields; clients send numeric IDs such as record_uid.
    model_config: ClassVar[ConfigDict] = ConfigDict(coerce_numbers_to_str=True)
