"""Tests for OtelExporter."""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from ccs.adapters.ccsstore import CCSStore
from ccs.adapters.events import StoreMetricEvent
from ccs.adapters.telemetry.otel import OtelExporter
from langgraph.store.base import GetOp, PutOp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_and_reader() -> tuple[MeterProvider, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider, reader


def _fake_event(operation: str = "put", cache_hit: bool = False, tokens: int = 50) -> StoreMetricEvent:
    return StoreMetricEvent(
        operation=operation,
        namespace=("agent", "shared"),
        key="plan",
        agent_name="planner",
        tokens_consumed=tokens,
        cache_hit=cache_hit,
        tick=1,
    )


def _collect_metrics(reader: InMemoryMetricReader) -> dict[str, list]:
    """Return {metric_name: [data_point, ...]} from the reader."""
    metrics: dict[str, list] = {}
    data = reader.get_metrics_data()
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                metrics[metric.name] = list(metric.data.data_points)
    return metrics


# ---------------------------------------------------------------------------
# Basic forwarding
# ---------------------------------------------------------------------------

def test_otel_put_records_operations_counter() -> None:
    provider, reader = _provider_and_reader()
    exporter = OtelExporter(meter_provider=provider)
    exporter.on_event(_fake_event(operation="put", tokens=100))

    metrics = _collect_metrics(reader)
    assert "ccs.store.operations" in metrics
    points = metrics["ccs.store.operations"]
    assert len(points) == 1
    assert points[0].value == 1
    assert points[0].attributes["ccs.operation"] == "put"
    assert points[0].attributes["ccs.cache_hit"] is False


def test_otel_put_records_tokens_counter() -> None:
    provider, reader = _provider_and_reader()
    exporter = OtelExporter(meter_provider=provider)
    exporter.on_event(_fake_event(operation="put", tokens=100))

    metrics = _collect_metrics(reader)
    assert "ccs.store.tokens_consumed" in metrics
    points = metrics["ccs.store.tokens_consumed"]
    assert points[0].value == 100


def test_otel_cache_hit_get_records_one_token() -> None:
    provider, reader = _provider_and_reader()
    exporter = OtelExporter(meter_provider=provider)
    exporter.on_event(_fake_event(operation="get", cache_hit=True, tokens=1))

    metrics = _collect_metrics(reader)
    token_points = metrics["ccs.store.tokens_consumed"]
    assert token_points[0].value == 1
    assert token_points[0].attributes["ccs.cache_hit"] is True


def test_otel_cache_miss_get_records_full_tokens() -> None:
    provider, reader = _provider_and_reader()
    exporter = OtelExporter(meter_provider=provider)
    exporter.on_event(_fake_event(operation="get", cache_hit=False, tokens=80))

    metrics = _collect_metrics(reader)
    token_points = metrics["ccs.store.tokens_consumed"]
    assert token_points[0].value == 80
    assert token_points[0].attributes["ccs.cache_hit"] is False


def test_otel_multiple_events_accumulate() -> None:
    provider, reader = _provider_and_reader()
    exporter = OtelExporter(meter_provider=provider)
    for _ in range(3):
        exporter.on_event(_fake_event(operation="get", tokens=50))

    metrics = _collect_metrics(reader)
    # Counter accumulates — all 3 share the same attributes so they roll into one point
    token_points = metrics["ccs.store.tokens_consumed"]
    assert sum(p.value for p in token_points) == 150


# ---------------------------------------------------------------------------
# No-op path (no SDK configured)
# ---------------------------------------------------------------------------

def test_otel_no_sdk_no_exception() -> None:
    # OtelExporter with the default global provider (no SDK in test env) must not raise
    exporter = OtelExporter()
    exporter.on_event(_fake_event())  # must complete without exception


# ---------------------------------------------------------------------------
# Integration: CCSStore + OtelExporter
# ---------------------------------------------------------------------------

def test_ccsstore_otel_records_put_and_get() -> None:
    provider, reader = _provider_and_reader()
    exporter = OtelExporter(meter_provider=provider)
    store = CCSStore(strategy="lazy", telemetry=exporter)

    store.batch([PutOp(namespace=("planner", "shared"), key="plan", value={"v": 1})])
    store.batch([GetOp(namespace=("planner", "shared"), key="plan")])

    metrics = _collect_metrics(reader)
    ops = metrics["ccs.store.operations"]
    operations = {p.attributes["ccs.operation"] for p in ops}
    assert "put" in operations
    assert "get" in operations
