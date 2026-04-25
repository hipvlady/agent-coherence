"""Tests for LangSmithExporter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("langsmith")

from ccs.adapters.ccsstore import CCSStore
from ccs.adapters.events import StoreMetricEvent
from ccs.adapters.telemetry.langsmith import LangSmithExporter
from langgraph.store.base import PutOp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_event(operation: str = "get", cache_hit: bool = True, tokens: int = 1, tick: int = 2) -> StoreMetricEvent:
    return StoreMetricEvent(
        operation=operation,
        namespace=("agent", "shared"),
        key="plan",
        agent_name="researcher",
        tokens_consumed=tokens,
        cache_hit=cache_hit,
        tick=tick,
    )


# ---------------------------------------------------------------------------
# Happy path — active run
# ---------------------------------------------------------------------------

def test_langsmith_calls_add_metadata_when_run_active() -> None:
    exporter = LangSmithExporter()
    mock_run = MagicMock()

    with patch("langsmith.run_helpers.get_current_run_tree", return_value=mock_run):
        exporter.on_event(_fake_event())

    mock_run.add_metadata.assert_called_once()
    metadata = mock_run.add_metadata.call_args[0][0]
    assert "ccs.operation" in metadata
    assert metadata["ccs.operation"] == "get"


def test_langsmith_metadata_contains_all_fields() -> None:
    exporter = LangSmithExporter()
    mock_run = MagicMock()
    event = _fake_event(operation="put", cache_hit=False, tokens=80, tick=5)

    with patch("langsmith.run_helpers.get_current_run_tree", return_value=mock_run):
        exporter.on_event(event)

    metadata = mock_run.add_metadata.call_args[0][0]
    assert metadata["ccs.operation"] == "put"
    assert metadata["ccs.agent_name"] == "researcher"
    assert metadata["ccs.tokens_consumed"] == 80
    assert metadata["ccs.cache_hit"] is False
    assert metadata["ccs.tick"] == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_langsmith_no_active_run_does_not_call_add_metadata() -> None:
    exporter = LangSmithExporter()

    with patch("langsmith.run_helpers.get_current_run_tree", return_value=None):
        exporter.on_event(_fake_event())  # must not raise

    # No add_metadata call possible since we have no mock_run to assert on —
    # the test passes if no exception is raised.


def test_langsmith_no_active_run_no_exception() -> None:
    exporter = LangSmithExporter()
    with patch("langsmith.run_helpers.get_current_run_tree", return_value=None):
        # Multiple calls — still no exception
        for _ in range(3):
            exporter.on_event(_fake_event())


# ---------------------------------------------------------------------------
# Integration: CCSStore + LangSmithExporter
# ---------------------------------------------------------------------------

def test_ccsstore_langsmith_receives_metadata_after_put() -> None:
    mock_run = MagicMock()
    exporter = LangSmithExporter()
    store = CCSStore(strategy="lazy", telemetry=exporter)

    with patch("langsmith.run_helpers.get_current_run_tree", return_value=mock_run):
        store.batch([PutOp(namespace=("planner", "shared"), key="plan", value={"v": 1})])

    mock_run.add_metadata.assert_called_once()
    metadata = mock_run.add_metadata.call_args[0][0]
    assert metadata["ccs.operation"] == "put"
