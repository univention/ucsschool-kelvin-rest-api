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
