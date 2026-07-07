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

    # Outbound UDM REST calls go through aiohttp; this global patch emits an
    # http.client.duration histogram for every request (no router changes needed).
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

    AioHttpClientInstrumentor().instrument(meter_provider=provider)
    logger.info("OpenTelemetry HTTP metrics exporter configured (server + UDM client).")


# SQL statement keywords we expose as the low-cardinality `db.operation` attribute;
# anything else is bucketed as OTHER so raw statement text never becomes a label.
_SQL_OPERATIONS = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "COMMIT", "ROLLBACK", "BEGIN"}
)


def _sql_operation(statement: str) -> str:
    stmt = (statement or "").lstrip()
    if not stmt:
        return "OTHER"
    first = stmt.split(None, 1)[0].upper()
    return first if first in _SQL_OPERATIONS else "OTHER"


def instrument_sqlalchemy_metrics(app: FastAPI, engine, logger: logging.Logger) -> None:
    """Instrument the DB engine for metrics. Call from lifespan startup (per worker).

    ``engine`` is the async engine built by ``build_engine``; instrumentation is applied
    to its underlying sync engine. Emits the connection-pool gauge
    (``db.client.connections.usage``) via ``SQLAlchemyInstrumentor`` plus a custom
    ``db.client.query.duration`` histogram (ms, tagged with ``db.operation``) recorded
    from cursor-execute events, since the instrumentor itself only spans queries.
    """
    if not metrics_enabled():
        return

    import time

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from sqlalchemy import event

    provider = getattr(app.state, "otel_meter_provider", None)
    sync_engine = engine.sync_engine

    SQLAlchemyInstrumentor().instrument(engine=sync_engine, meter_provider=provider)

    meter = provider.get_meter(__name__)
    query_duration = meter.create_histogram(
        "db.client.query.duration", unit="ms", description="Duration of database queries."
    )

    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_otel_query_start", []).append(time.perf_counter())

    def _after(conn, cursor, statement, parameters, context, executemany):
        stack = conn.info.get("_otel_query_start")
        if not stack:
            return
        elapsed_ms = (time.perf_counter() - stack.pop()) * 1000.0
        query_duration.record(elapsed_ms, {"db.operation": _sql_operation(statement)})

    event.listen(sync_engine, "before_cursor_execute", _before)
    event.listen(sync_engine, "after_cursor_execute", _after)
    logger.info("OpenTelemetry SQLAlchemy metrics enabled.")


def shutdown_meter_provider(app: FastAPI) -> None:
    """Uninstrument outbound instrumentors, then flush and shut down the meter provider."""
    if metrics_enabled():
        from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        AioHttpClientInstrumentor().uninstrument()
        SQLAlchemyInstrumentor().uninstrument()

    provider = getattr(app.state, "otel_meter_provider", None)
    if provider is not None:
        provider.shutdown()
