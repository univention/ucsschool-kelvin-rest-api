"""OpenTelemetry metrics for the kelvin-connector.

Metrics-only, gated behind the UCSSCHOOL_KELVIN_OTEL_METRICS_ENABLED environment
variable, exported via OTLP (configured through the standard OTEL_* env vars). The
connector is a single asyncio process, so a single MeterProvider is installed in
main() and shut down when the process exits.

This mirrors the kelvin-api telemetry wiring, but the connector is a separate package
(kelvin-api is not a dependency here) so the DB helper is duplicated, and log metrics
use a loguru sink rather than a stdlib logging handler.
"""

from __future__ import annotations

import os

OTEL_METRICS_ENABLED_ENV = "UCSSCHOOL_KELVIN_OTEL_METRICS_ENABLED"
DEFAULT_SERVICE_NAME = "kelvin-connector"

# SQL keywords exposed as the low-cardinality `db.operation` attribute; anything else
# is bucketed as OTHER so raw statement text never becomes a label.
_SQL_OPERATIONS = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "COMMIT", "ROLLBACK", "BEGIN"}
)


def metrics_enabled() -> bool:
    """True if OTel metrics export is enabled via the environment flag."""
    return os.environ.get(OTEL_METRICS_ENABLED_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def setup_meter_provider(logger):
    """Install the OTLP-backed MeterProvider. Returns the provider, or None if disabled."""
    if not metrics_enabled():
        return None

    from importlib.metadata import PackageNotFoundError, version

    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource

    try:
        service_version = version("kelvin-connector")
    except PackageNotFoundError:  # pragma: no cover - only when running from an unbuilt tree
        service_version = "unknown"

    resource = Resource.create(
        {
            SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME),
            SERVICE_VERSION: service_version,
        }
    )
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    logger.info("OpenTelemetry metrics exporter configured.")
    return provider


def _sql_operation(statement: str) -> str:
    stmt = (statement or "").lstrip()
    if not stmt:
        return "OTHER"
    first = stmt.split(None, 1)[0].upper()
    return first if first in _SQL_OPERATIONS else "OTHER"


def instrument_sqlalchemy_metrics(engine, provider, logger) -> None:
    """Instrument the connector's async DB engine for metrics.

    Emits the connection-pool gauge (db.client.connections.usage) via the SQLAlchemy
    instrumentor plus a custom db.client.query.duration histogram (ms, tagged with
    db.operation) recorded from cursor-execute events.
    """
    if provider is None:
        return

    import time

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from sqlalchemy import event

    sync_engine = engine.sync_engine
    SQLAlchemyInstrumentor().instrument(engine=sync_engine, meter_provider=provider)

    query_duration = provider.get_meter(__name__).create_histogram(
        "db.client.query.duration", unit="ms", description="Duration of database queries."
    )

    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_otel_query_start", []).append(time.perf_counter())

    def _after(conn, cursor, statement, parameters, context, executemany):
        stack = conn.info.get("_otel_query_start")
        if not stack:  # pragma: no cover - defensive: _after always follows _before
            return
        elapsed_ms = (time.perf_counter() - stack.pop()) * 1000.0
        query_duration.record(elapsed_ms, {"db.operation": _sql_operation(statement)})

    event.listen(sync_engine, "before_cursor_execute", _before)
    event.listen(sync_engine, "after_cursor_execute", _after)
    logger.info("OpenTelemetry SQLAlchemy metrics enabled.")


def instrument_log_metrics(provider, logger) -> None:
    """Count emitted loguru records by level/component into `kelvin.log.records`.

    Adds a loguru sink (the connector uses loguru, not stdlib logging). No-op when
    telemetry is disabled.
    """
    if provider is None:
        return

    counter = provider.get_meter(__name__).create_counter(
        "kelvin.log.records", unit="{record}", description="Log records emitted, by level."
    )

    def _sink(message) -> None:
        try:
            record = message.record
            counter.add(
                1,
                {
                    "level": record["level"].name,
                    "component": (record["name"] or "root").split(".", 1)[0],
                },
            )
        except Exception:  # pragma: no cover - never disrupt logging
            pass

    logger.add(_sink, level="TRACE")
    logger.info("OpenTelemetry log-record metrics enabled.")


def event_metrics():
    """Create the per-event counter and duration histogram from the global meter.

    Uses the global meter provider, which is a no-op until setup_meter_provider()
    installs the real one -- so the consumer can record unconditionally.
    """
    from opentelemetry import metrics

    meter = metrics.get_meter("kelvin_connector")
    counter = meter.create_counter(
        "kelvin.connector.events", unit="{event}", description="Provisioning events processed."
    )
    duration = meter.create_histogram(
        "kelvin.connector.event.duration", unit="ms", description="Event processing duration."
    )
    return counter, duration


def event_labels(event) -> dict:
    """Best-effort {object_type, operation} labels for a provisioning event.

    object_type comes from the event topic; operation is inferred from whether the
    body carries old/new state. Missing/odd shapes fall back to "unknown".
    """
    object_type = "unknown"
    operation = "unknown"
    try:
        object_type = event.get("topic") or "unknown"
        body = event.get("body") or {}
        has_new = bool(body.get("new"))
        has_old = bool(body.get("old"))
        if has_new and not has_old:
            operation = "create"
        elif has_new and has_old:
            operation = "modify"
        elif has_old and not has_new:
            operation = "remove"
    except Exception:  # pragma: no cover - labels must never break processing
        pass
    return {"object_type": object_type, "operation": operation}
