"""Tests for the OpenTelemetry HTTP metrics wiring (service/telemetry.py)."""

import logging

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from ucsschool.kelvin.service import telemetry

logger = logging.getLogger(__name__)

ENABLE_ENV = "UCSSCHOOL_KELVIN_OTEL_METRICS_ENABLED"


def _fresh_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_metrics_disabled_by_default(monkeypatch):
    """Without the enable flag, instrumentation and provider setup are no-ops."""
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    # env_or_ucr would otherwise fall back to UCR, which is unset in tests -> disabled.
    assert telemetry.metrics_enabled() is False

    app = _fresh_app()
    telemetry.instrument_fastapi_metrics(app, logger)
    telemetry.setup_meter_provider(app, logger)

    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is False
    assert getattr(app.state, "otel_meter_provider", None) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("", False),
        ("nonsense", False),
    ],
)
def test_metrics_enabled_flag_parsing(monkeypatch, value, expected):
    monkeypatch.setenv(ENABLE_ENV, value)
    assert telemetry.metrics_enabled() is expected


def test_instrument_fastapi_metrics_instruments_app(monkeypatch):
    """With the flag on, the app is marked instrumented by OpenTelemetry."""
    monkeypatch.setenv(ENABLE_ENV, "true")
    app = _fresh_app()
    telemetry.instrument_fastapi_metrics(app, logger)
    assert app._is_instrumented_by_opentelemetry is True


def test_instrumented_app_records_http_server_metrics():
    """An instrumented app records `http.server.*` metrics for served requests.

    Uses an explicit in-memory provider (not the process-global one, which can only
    be set once) to keep the assertion independent of test ordering.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    app = _fresh_app()
    FastAPIInstrumentor().instrument_app(app, meter_provider=provider)
    try:
        with TestClient(app) as client:
            assert client.get("/ping").status_code == 200

        metric_names = {
            metric.name
            for resource_metric in reader.get_metrics_data().resource_metrics
            for scope_metric in resource_metric.scope_metrics
            for metric in scope_metric.metrics
        }
        assert any(name.startswith("http.server") for name in metric_names), metric_names
    finally:
        FastAPIInstrumentor().uninstrument_app(app)


def _metrics_by_name(reader):
    """Map metric name -> list of data points from an InMemoryMetricReader."""
    out = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                out.setdefault(metric.name, []).extend(metric.data.data_points)
    return out


def test_sqlalchemy_metrics_record_query_duration(monkeypatch):
    """instrument_sqlalchemy_metrics records a db.client.query.duration histogram
    tagged with the SQL operation."""
    monkeypatch.setenv(ENABLE_ENV, "true")
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from sqlalchemy import create_engine, text

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    # Test double for an AsyncEngine: instrument_sqlalchemy_metrics only touches
    # `.sync_engine`, so a plain sync engine behind that attribute exercises the
    # same code path without pulling in an async sqlite driver.
    sync_engine = create_engine("sqlite://")

    class _AsyncEngineShim:
        pass

    shim = _AsyncEngineShim()
    shim.sync_engine = sync_engine

    app = _fresh_app()
    app.state.otel_meter_provider = provider
    try:
        telemetry.instrument_sqlalchemy_metrics(app, shim, logger)
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        metrics = _metrics_by_name(reader)
        assert "db.client.query.duration" in metrics, list(metrics)
        operations = {dp.attributes.get("db.operation") for dp in metrics["db.client.query.duration"]}
        assert "SELECT" in operations, operations
    finally:
        SQLAlchemyInstrumentor().uninstrument()


def test_sql_operation_buckets_unknown_as_other():
    assert telemetry._sql_operation("select * from t") == "SELECT"
    assert telemetry._sql_operation("  INSERT INTO t VALUES (1)") == "INSERT"
    assert telemetry._sql_operation("VACUUM") == "OTHER"
    assert telemetry._sql_operation("") == "OTHER"


def test_aiohttp_client_metrics_record_duration(monkeypatch):
    """The aiohttp-client instrumentor emits http.client.duration for outbound calls
    (this is how UDM REST latency is captured)."""
    import asyncio

    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    async def _probe():
        from aiohttp import ClientSession, web

        async def handler(request):
            return web.Response(text="ok")

        server = web.Application()
        server.router.add_get("/probe", handler)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                async with session.get(f"http://127.0.0.1:{port}/probe") as resp:
                    await resp.text()
        finally:
            await runner.cleanup()

    AioHttpClientInstrumentor().instrument(meter_provider=provider)
    try:
        asyncio.run(_probe())
        metrics = _metrics_by_name(reader)
        assert any(name.startswith("http.client") for name in metrics), list(metrics)
    finally:
        AioHttpClientInstrumentor().uninstrument()
