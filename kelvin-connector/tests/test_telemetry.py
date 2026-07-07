"""Tests for kelvin_connector.telemetry (OpenTelemetry metrics wiring)."""

from unittest.mock import MagicMock, patch

import pytest
from kelvin_connector import telemetry
from loguru import logger

ENABLE_ENV = "UCSSCHOOL_KELVIN_OTEL_METRICS_ENABLED"


def _metrics_by_name(reader):
    out = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                out.setdefault(metric.name, []).extend(metric.data.data_points)
    return out


@pytest.mark.parametrize(
    "value,expected",
    [("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
     ("false", False), ("0", False), ("", False), ("nonsense", False)],
)
def test_metrics_enabled_parsing(monkeypatch, value, expected):
    monkeypatch.setenv(ENABLE_ENV, value)
    assert telemetry.metrics_enabled() is expected


def test_metrics_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    assert telemetry.metrics_enabled() is False


def test_setup_meter_provider_disabled_returns_none(monkeypatch):
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    assert telemetry.setup_meter_provider(logger) is None


def test_setup_meter_provider_enabled_builds_provider(monkeypatch):
    monkeypatch.setenv(ENABLE_ENV, "true")
    # Avoid a real OTLP exporter (network) and the process-global set_meter_provider.
    with (
        patch("opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"),
        patch("opentelemetry.metrics.set_meter_provider") as set_provider,
    ):
        provider = telemetry.setup_meter_provider(logger)
    assert provider is not None
    set_provider.assert_called_once_with(provider)


@pytest.mark.parametrize(
    "statement,expected",
    [("select * from t", "SELECT"), ("  INSERT INTO t VALUES (1)", "INSERT"),
     ("VACUUM", "OTHER"), ("", "OTHER")],
)
def test_sql_operation(statement, expected):
    assert telemetry._sql_operation(statement) == expected


def test_instrument_sqlalchemy_metrics_disabled_is_noop():
    engine = MagicMock()
    telemetry.instrument_sqlalchemy_metrics(engine, None, logger)
    engine.sync_engine.assert_not_called()  # never touched when provider is None


def test_instrument_sqlalchemy_metrics_records_query_duration():
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from sqlalchemy import create_engine, text

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    # Test double for an AsyncEngine: only `.sync_engine` is used.
    sync_engine = create_engine("sqlite://")
    shim = MagicMock()
    shim.sync_engine = sync_engine
    try:
        telemetry.instrument_sqlalchemy_metrics(shim, provider, logger)
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        metrics = _metrics_by_name(reader)
        assert "db.client.query.duration" in metrics, list(metrics)
        ops = {dp.attributes.get("db.operation") for dp in metrics["db.client.query.duration"]}
        assert "SELECT" in ops, ops
    finally:
        SQLAlchemyInstrumentor().uninstrument()


def test_instrument_log_metrics_disabled_is_noop():
    # No provider -> no sink added; must not raise.
    telemetry.instrument_log_metrics(None, logger)


def test_instrument_log_metrics_records_by_level_and_component():
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    sink_ids_before = set(logger._core.handlers)
    telemetry.instrument_log_metrics(provider, logger)
    try:
        logger.bind().warning("a warning")
        metrics = _metrics_by_name(reader)
        assert "kelvin.log.records" in metrics, list(metrics)
        levels = {dp.attributes.get("level") for dp in metrics["kelvin.log.records"]}
        assert "WARNING" in levels, levels
    finally:
        # remove only the sink we added
        for hid in set(logger._core.handlers) - sink_ids_before:
            logger.remove(hid)


def test_event_metrics_returns_instruments():
    counter, duration = telemetry.event_metrics()
    assert hasattr(counter, "add")
    assert hasattr(duration, "record")


@pytest.mark.parametrize(
    "event,expected_op",
    [
        ({"topic": "users/user", "body": {"new": {"x": 1}}}, "create"),
        ({"topic": "users/user", "body": {"old": {"x": 1}, "new": {"x": 2}}}, "modify"),
        ({"topic": "users/user", "body": {"old": {"x": 1}}}, "remove"),
        ({"topic": "users/user", "body": {}}, "unknown"),
        ({}, "unknown"),
    ],
)
def test_event_labels(event, expected_op):
    labels = telemetry.event_labels(event)
    assert labels["operation"] == expected_op
    assert "object_type" in labels
