import logging
from functools import partial
from typing import Any, Dict, List

from asgi_correlation_id import CorrelationIdMiddleware
from asgi_correlation_id.context import correlation_id
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, ORJSONResponse

from ucsschool.lib.models.attributes import ValidationError as SchooLibValidationError
from ucsschool.lib.models.base import NoObject
from udm_rest_client import UdmError


async def udm_exception_handler(
    request: Request, exc: UdmError, logger: logging.Logger
) -> ORJSONResponse:
    """Format unhandled UDM exceptions and return in a standard JSON format."""

    error_type = f"UdmError:{exc.__class__.__name__}"
    errors: List[Dict[str, Any]]
    if exc.error is not None:
        errors = [
            {"loc": (location,), "msg": message, "type": error_type}
            for (location, message) in exc.error.items()
        ]
    elif exc.reason is not None:
        errors = [{"loc": (), "msg": exc.reason, "type": error_type}]
    else:
        errors = [{"loc": (), "msg": str(exc), "type": error_type}]

    status_code = exc.status or 500

    logger.error(f"Encountered exception {exc} responding with {errors}")

    return ORJSONResponse(
        content=jsonable_encoder({"detail": errors}),
        status_code=status_code,
        headers={
            CorrelationIdMiddleware.header_name: correlation_id.get() or "",
            "Access-Control-Expose-Headers": CorrelationIdMiddleware.header_name,
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception, logger: logging.Logger
) -> JSONResponse:
    """Add Correlation-ID to HTTP 500."""
    logger.exception(f"While responding to {request.method!s} {request.url!s}: {exc!s}")
    return await http_exception_handler(
        request,
        HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal server error",
            headers={
                CorrelationIdMiddleware.header_name: correlation_id.get() or "",
                "Access-Control-Expose-Headers": CorrelationIdMiddleware.header_name,
            },
        ),
    )


async def no_object_exception_handler(request: Request, exc: NoObject) -> ORJSONResponse:
    return ORJSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"message": str(exc)})


async def school_lib_validation_exception_handler(
    request: Request, exc: SchooLibValidationError
) -> ORJSONResponse:
    return ORJSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"message": str(exc)})


def add_exception_handlers(app: FastAPI, logger: logging.Logger) -> None:
    app.add_exception_handler(UdmError, partial(udm_exception_handler, logger=logger))
    app.add_exception_handler(Exception, partial(unhandled_exception_handler, logger=logger))
    app.add_exception_handler(NoObject, no_object_exception_handler)
    app.add_exception_handler(SchooLibValidationError, school_lib_validation_exception_handler)
