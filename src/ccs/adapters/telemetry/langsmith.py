# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""LangSmith run metadata exporter for CCSStore operations."""

from __future__ import annotations

import logging

from ccs.adapters.events import StoreMetricEvent, TelemetryExporter

logger = logging.getLogger(__name__)


class LangSmithExporter(TelemetryExporter):
    """Attaches CCSStore operation metadata to the active LangSmith run.

    Requires the ``langsmith`` package (``pip install "agent-coherence[langsmith]"``).
    If no active LangSmith run is found, events are silently discarded.

    Usage::

        store = CCSStore(strategy="lazy", telemetry="langsmith")
        # or with an explicit project:
        from ccs.adapters.telemetry.langsmith import LangSmithExporter
        store = CCSStore(strategy="lazy", telemetry=LangSmithExporter())
    """

    def on_event(self, event: StoreMetricEvent) -> None:
        try:
            from langsmith import run_helpers  # noqa: PLC0415
        except ImportError:
            return

        run = run_helpers.get_current_run_tree()
        if run is None:
            return

        run.add_metadata(
            {
                "ccs.operation": event.operation,
                "ccs.agent_name": event.agent_name,
                "ccs.tokens_consumed": event.tokens_consumed,
                "ccs.cache_hit": event.cache_hit,
                "ccs.tick": event.tick,
            }
        )
