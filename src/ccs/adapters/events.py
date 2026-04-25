# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Shared event types for CCSStore adapters.

Kept in a separate module so both ccsstore.py and the telemetry sub-package
can import StoreMetricEvent without creating a circular dependency.
"""

from __future__ import annotations

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
