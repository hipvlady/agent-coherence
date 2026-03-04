"""Tests for framework adapter integration helpers."""

from __future__ import annotations

from ccs.adapters.autogen import AutoGenAdapter
from ccs.adapters.crewai import CrewAIAdapter
from ccs.adapters.langgraph import LangGraphAdapter
from ccs.core.states import MESIState


def test_langgraph_adapter_propagates_invalidation_then_refresh() -> None:
    adapter = LangGraphAdapter(strategy_name="lazy")
    artifact = adapter.register_artifact(name="plan.md", content="v1", size_tokens=128)
    adapter.register_agent("planner")
    adapter.register_agent("researcher")

    planner_context = adapter.before_node(agent_name="planner", artifact_ids=[artifact.id], now_tick=1)
    assert planner_context[artifact.id]["version"] == 1
    assert planner_context[artifact.id]["content"] == "v1"
    adapter.before_node(agent_name="researcher", artifact_ids=[artifact.id], now_tick=1)

    versions = adapter.commit_outputs(
        agent_name="planner",
        writes={artifact.id: "v2"},
        now_tick=2,
    )
    assert versions[artifact.id] == 2

    researcher_entry = adapter.core.runtime("researcher").cache.get(artifact.id)
    assert researcher_entry is not None
    assert researcher_entry.state == MESIState.INVALID

    refreshed = adapter.before_node(agent_name="researcher", artifact_ids=[artifact.id], now_tick=3)
    assert refreshed[artifact.id]["version"] == 2
    assert refreshed[artifact.id]["content"] == "v2"


def test_crewai_adapter_task_hooks_roundtrip_content() -> None:
    adapter = CrewAIAdapter(strategy_name="lazy")
    artifact = adapter.register_artifact(name="analysis.json", content='{"summary":"v1"}')
    adapter.register_agent("author")
    adapter.register_agent("reviewer")

    initial = adapter.prepare_task_context(agent_name="author", artifact_ids=[artifact.id], now_tick=1)
    assert initial[artifact.id] == '{"summary":"v1"}'

    new_version = adapter.commit_task_artifact(
        agent_name="author",
        artifact_id=artifact.id,
        content='{"summary":"v2"}',
        now_tick=2,
    )
    assert new_version == 2

    reviewer_context = adapter.prepare_task_context(
        agent_name="reviewer",
        artifact_ids=[artifact.id],
        now_tick=3,
    )
    assert reviewer_context[artifact.id] == '{"summary":"v2"}'


def test_autogen_adapter_turn_hooks_roundtrip_content() -> None:
    adapter = AutoGenAdapter(strategy_name="lazy")
    artifact = adapter.register_artifact(name="facts.md", content="v1")
    adapter.register_agent("assistant")
    adapter.register_agent("planner")

    pre_turn = adapter.pre_turn_context(agent_name="assistant", artifact_ids=[artifact.id], now_tick=1)
    assert pre_turn[artifact.id] == "v1"

    versions = adapter.post_turn_commit(
        agent_name="assistant",
        updates={artifact.id: "v2"},
        now_tick=2,
    )
    assert versions[artifact.id] == 2

    planner_view = adapter.pre_turn_context(agent_name="planner", artifact_ids=[artifact.id], now_tick=3)
    assert planner_view[artifact.id] == "v2"
