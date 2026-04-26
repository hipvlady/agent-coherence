# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Shared event types and telemetry protocol for CCSStore adapters.

Kept in a leaf module so ccsstore.py, telemetry/__init__.py, and concrete
exporter implementations (otel.py, langsmith.py) can all import from here
without creating circular dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StoreMetricEvent:
    """Emitted by CCSStore for each artifact operation when on_metric is set."""

    operation: str
    namespace: tuple[str, ...]
    key: str
    agent_name: str
    tokens_consumed: int
    cache_hit: bool
    tick: int
    tokens_saved_estimate: int = 0


class TelemetryExporter(ABC):
    """Contract for CCSStore telemetry backends."""

    @abstractmethod
    def on_event(self, event: StoreMetricEvent) -> None:
        """Called after each CCSStore operation."""


class NoOpTelemetryExporter(TelemetryExporter):
    """Default exporter — discards all events at zero cost."""

    def on_event(self, event: StoreMetricEvent) -> None:
        pass
