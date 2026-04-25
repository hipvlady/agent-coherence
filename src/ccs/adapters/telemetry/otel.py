# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""OpenTelemetry metrics exporter for CCSStore operations."""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Meter

from ccs.adapters.events import StoreMetricEvent, TelemetryExporter

# Package version for meter instrumentation scope
_INSTRUMENTATION_VERSION = "0.2.0"


class OtelExporter(TelemetryExporter):
    """Forwards CCSStore StoreMetricEvents to OpenTelemetry Counter instruments.

    Uses the globally configured MeterProvider unless an explicit one is injected.
    If no SDK is configured, the OTel no-op path discards all records at zero cost.

    Usage::

        # Zero-config (uses global OTel provider if configured)
        store = CCSStore(strategy="lazy", telemetry="opentelemetry")

        # Explicit provider (useful for testing)
        from ccs.adapters.telemetry.otel import OtelExporter
        store = CCSStore(strategy="lazy", telemetry=OtelExporter(meter_provider=my_provider))
    """

    def __init__(self, meter_provider: metrics.MeterProvider | None = None) -> None:
        provider = meter_provider or metrics.get_meter_provider()
        self._meter: Meter = provider.get_meter(
            "ccs.adapters.ccsstore",
            version=_INSTRUMENTATION_VERSION,
        )
        # Instruments are singletons per meter — create once, not per event.
        self._ops_counter: Counter = self._meter.create_counter(
            name="ccs.store.operations",
            unit="{operation}",
            description="Count of CCSStore operations",
        )
        self._tokens_counter: Counter = self._meter.create_counter(
            name="ccs.store.tokens_consumed",
            unit="{token}",
            description="Tokens consumed by CCSStore operations",
        )

    def on_event(self, event: StoreMetricEvent) -> None:
        attributes = {
            "ccs.operation": event.operation,
            "ccs.agent_name": event.agent_name,
            "ccs.cache_hit": event.cache_hit,
        }
        self._ops_counter.add(1, attributes)
        self._tokens_counter.add(event.tokens_consumed, attributes)
