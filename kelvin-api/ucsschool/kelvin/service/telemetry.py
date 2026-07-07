"""OpenTelemetry HTTP metrics setup for the Kelvin REST API.

Metrics-only, FastAPI-only instrumentation, gated behind an enable flag so it stays
off by default. All exporter configuration is read natively by the SDK from the
standard ``OTEL_*`` environment variables (endpoint, headers, protocol, ...).

Two-step wiring, because of gunicorn's pre-fork model and how the FastAPI
instrumentation hooks Starlette:

* ``instrument_fastapi_metrics(app)`` runs at import time (before the app is ever
  called). ``FastAPIInstrumentor`` patches ``Starlette.build_middleware_stack``,
  which Starlette invokes lazily on the very first call -- the ASGI ``lifespan``
  scope -- so it must be in place before then. No provider is passed, so the OTel
  API's global *proxy* meter is used.
* ``setup_meter_provider(app)`` runs from the app lifespan (once per worker, i.e.
  post-fork) and installs the real ``MeterProvider`` whose exporter owns a
  background thread. Creating that thread post-fork keeps it in the worker rather
  than the gunicorn master. Setting the global meter provider upgrades the proxy
  meter/instruments created above so recorded metrics are exported.
"""

import logging
import os

from fastapi import FastAPI

OTEL_METRICS_ENABLED_UCRV = "ucsschool/kelvin/otel_metrics_enabled"
DEFAULT_SERVICE_NAME = "kelvin-api"


def metrics_enabled() -> bool:
    """Read the enable flag from env/UCR, defaulting to disabled if unset."""
    from ucsschool.lib.models.utils import env_or_ucr

    try:
        value = env_or_ucr(OTEL_METRICS_ENABLED_UCRV)
    except KeyError:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def instrument_fastapi_metrics(app: FastAPI, logger: logging.Logger) -> None:
    """Instrument ``app`` for HTTP metrics. Call at import, before the app is served.

    No-op unless the enable flag is truthy. Only metrics are produced: no
    ``TracerProvider`` is installed, so the global tracer provider stays at its
    API-level no-op and no trace data is emitted.
    """
    if not metrics_enabled():
        logger.debug("OpenTelemetry metrics disabled (%s not set).", OTEL_METRICS_ENABLED_UCRV)
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    # meter_provider left unset: the global (proxy) meter is used and upgraded once
    # setup_meter_provider() installs the real provider during lifespan startup.
    FastAPIInstrumentor().instrument_app(app)
    logger.info("OpenTelemetry FastAPI metrics instrumentation enabled.")


def setup_meter_provider(app: FastAPI, logger: logging.Logger) -> None:
    """Install the OTLP-backed ``MeterProvider``. Call from lifespan startup (per worker)."""
    if not metrics_enabled():
        return

    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource

    from ..constants import APP_VERSION

    resource = Resource.create(
        {
            SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
            SERVICE_VERSION: str(APP_VERSION),
        }
    )
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    app.state.otel_meter_provider = provider
    logger.info("OpenTelemetry HTTP metrics exporter configured.")


def shutdown_meter_provider(app: FastAPI) -> None:
    """Flush and shut down the meter provider if telemetry was enabled."""
    provider = getattr(app.state, "otel_meter_provider", None)
    if provider is not None:
        provider.shutdown()
