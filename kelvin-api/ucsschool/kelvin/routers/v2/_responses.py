# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Response helper for the v2 collection endpoints."""

from collections.abc import Sequence

from fastapi.responses import ORJSONResponse
from pydantic import BaseModel


def model_list_response(models: Sequence[BaseModel]) -> ORJSONResponse:
    """Serialise a collection response without FastAPI's generic encoder.

    Returning a ``Response`` short-circuits ``serialize_response``, which
    otherwise walks every object twice: once re-validating it against a clone
    of the response model, once through ``jsonable_encoder``. ``by_alias=True``
    mirrors what it would have produced, so the payload is unchanged.

    The route's ``response_model`` still drives the OpenAPI schema. What is
    given up is response *validation*: the payload goes out as the endpoint
    built it.
    """
    return ORJSONResponse([model.dict(by_alias=True) for model in models])
