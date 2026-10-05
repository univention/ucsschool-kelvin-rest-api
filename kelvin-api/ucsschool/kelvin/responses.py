# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import Any

import orjson
from fastapi.responses import JSONResponse
from typing_extensions import override


class ORJSONResponse(JSONResponse):
    """FastAPI's deprecated `ORJSONResponse`, kept so the response bodies stay byte-identical."""

    @override
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content, option=orjson.OPT_NON_STR_KEYS)
