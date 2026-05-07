# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Tests for per-agent content audit log (Units 1, 2, 3, 7)."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest

from ccs.agent.runtime import AgentRuntime, CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION
from ccs.coordinator.registry import ArtifactRegistry
from ccs.coordinator.service import CoordinatorService
from ccs.core.hashing import compute_content_hash
from ccs.strategies.lazy import LazyStrategy


# ---------------------------------------------------------------------------
# Unit 1: Hash utility and schema version constant
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    def test_empty_string(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_content_hash("") == expected

    def test_hello(self):
        expected = hashlib.sha256(b"hello").hexdigest()
        assert compute_content_hash("hello") == expected

    def test_deterministic(self):
        assert compute_content_hash("same") == compute_content_hash("same")

    def test_different_content_different_hash(self):
        assert compute_content_hash("a") != compute_content_hash("b")

    def test_utf8_encoding(self):
        content = "éàü"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert compute_content_hash(content) == expected


class TestSchemaVersionConstant:
    def test_starts_with_ccs(self):
        assert CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION.startswith("ccs.")

    def test_value(self):
        assert CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION == "ccs.content_audit.v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_ID = uuid4()
ARTIFACT_ID = uuid4()
INSTANCE_ID = "test-audit-instance"


def _audit_runtime(
    log: list[dict],
    *,
    coordinator: CoordinatorService | None = None,
    agent_id=AGENT_ID,
    audit_seq: list[int] | None = None,
) -> AgentRuntime:
    service = coordinator or CoordinatorService(ArtifactRegistry())
    return AgentRuntime(
        agent_id=agent_id,
        coordinator=service,
        strategy=LazyStrategy(),
        content_audit_log=log.append,
        audit_seq=audit_seq if audit_seq is not None else [0],
        agent_name="test-agent",
        instance_id=INSTANCE_ID,
    )


R1_FIELDS = {
    "tick", "agent_id", "agent_name", "artifact_id", "version",
    "content_hash", "source", "outcome", "sequence_number",
    "instance_id", "schema_version",
}


# ---------------------------------------------------------------------------
# Unit 2: _record_content_view and _record_search_view
# ---------------------------------------------------------------------------


class TestRecordContentView:
    def test_emits_all_r1_fields(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="hello",
            source="fetch", now_tick=10,
        )
        assert len(log) == 1
        assert set(log[0].keys()) == R1_FIELDS

    def test_source_matches(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        for src in ("cache_hit", "fetch", "broadcast", "write"):
            rt._record_content_view(
                artifact_id=ARTIFACT_ID, version=1, content="x",
                source=src, now_tick=1,
            )
        sources = [e["source"] for e in log]
        assert sources == ["cache_hit", "fetch", "broadcast", "write"]

    def test_outcome_content_with_hash(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        h = rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="hello",
            source="fetch", now_tick=1,
        )
        assert log[0]["outcome"] == "content"
        assert log[0]["content_hash"] == compute_content_hash("hello")
        assert h == compute_content_hash("hello")

    def test_outcome_content_for_empty_string_at_version_1(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        h = rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="",
            source="fetch", now_tick=1,
        )
        assert log[0]["outcome"] == "content"
        assert log[0]["content_hash"] == compute_content_hash("")
        assert log[0]["version"] == 1
        assert h is not None

    def test_outcome_empty_when_version_none(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        h = rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=None, content="",
            source="fetch", now_tick=1,
        )
        assert log[0]["outcome"] == "empty"
        assert log[0]["version"] is None
        assert log[0]["content_hash"] is None
        assert h is None

    def test_outcome_empty_when_version_zero(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        h = rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=0, content="",
            source="fetch", now_tick=1,
        )
        assert log[0]["outcome"] == "empty"
        assert log[0]["version"] is None
        assert log[0]["content_hash"] is None
        assert h is None

    def test_outcome_error_when_content_none(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        h = rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content=None,
            source="fetch", now_tick=1,
        )
        assert log[0]["outcome"] == "error"
        assert log[0]["version"] is None
        assert log[0]["content_hash"] is None
        assert h is None

    def test_sequence_number_increments(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        for i in range(3):
            rt._record_content_view(
                artifact_id=ARTIFACT_ID, version=1, content="x",
                source="fetch", now_tick=i,
            )
        assert [e["sequence_number"] for e in log] == [1, 2, 3]

    def test_sequence_number_rolls_back_on_exception(self):
        seq = [0]
        calls = []

        def failing_log(entry):
            calls.append(entry)
            raise RuntimeError("boom")

        rt = AgentRuntime(
            agent_id=AGENT_ID,
            coordinator=CoordinatorService(ArtifactRegistry()),
            strategy=LazyStrategy(),
            content_audit_log=failing_log,
            audit_seq=seq,
            agent_name="test",
            instance_id=INSTANCE_ID,
        )
        with pytest.raises(RuntimeError, match="boom"):
            rt._record_content_view(
                artifact_id=ARTIFACT_ID, version=1, content="x",
                source="fetch", now_tick=1,
            )
        assert seq[0] == 0

    def test_no_emission_when_callback_none(self):
        rt = AgentRuntime(
            agent_id=AGENT_ID,
            coordinator=CoordinatorService(ArtifactRegistry()),
            strategy=LazyStrategy(),
        )
        seq_before = rt._audit_seq[0]
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="x",
            source="fetch", now_tick=1,
        )
        assert rt._audit_seq[0] == seq_before

    def test_updates_content_by_artifact(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="new",
            source="fetch", now_tick=1,
        )
        assert rt._content_by_artifact[ARTIFACT_ID] == "new"

    def test_cache_hit_skips_dict_write(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._content_by_artifact[ARTIFACT_ID] = "existing"
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="existing",
            source="cache_hit", now_tick=1,
        )
        assert rt._content_by_artifact[ARTIFACT_ID] == "existing"
        assert len(log) == 1

    def test_tick_matches_now_tick(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="x",
            source="fetch", now_tick=42,
        )
        assert log[0]["tick"] == 42

    def test_agent_fields_match_constructor(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="x",
            source="fetch", now_tick=1,
        )
        assert log[0]["agent_id"] == str(AGENT_ID)
        assert log[0]["agent_name"] == "test-agent"
        assert log[0]["instance_id"] == INSTANCE_ID
        assert log[0]["schema_version"] == CCS_CONTENT_AUDIT_LOG_SCHEMA_VERSION

    def test_records_json_serializable(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="hello",
            source="fetch", now_tick=1,
        )
        roundtrip = json.loads(json.dumps(log[0]))
        assert roundtrip == log[0]


class TestRecordSearchView:
    def test_emits_source_search(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_search_view(
            artifact_id=ARTIFACT_ID, version=1, content="hello", now_tick=1,
        )
        assert len(log) == 1
        assert log[0]["source"] == "search"
        assert set(log[0].keys()) == R1_FIELDS

    def test_does_not_update_content_by_artifact(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_search_view(
            artifact_id=ARTIFACT_ID, version=1, content="hello", now_tick=1,
        )
        assert ARTIFACT_ID not in rt._content_by_artifact

    def test_shares_sequence_counter(self):
        log: list[dict] = []
        seq = [0]
        rt = _audit_runtime(log, audit_seq=seq)
        rt._record_content_view(
            artifact_id=ARTIFACT_ID, version=1, content="a",
            source="fetch", now_tick=1,
        )
        rt._record_search_view(
            artifact_id=ARTIFACT_ID, version=1, content="b", now_tick=2,
        )
        assert log[0]["sequence_number"] == 1
        assert log[1]["sequence_number"] == 2

    def test_no_emission_when_callback_none(self):
        rt = AgentRuntime(
            agent_id=AGENT_ID,
            coordinator=CoordinatorService(ArtifactRegistry()),
            strategy=LazyStrategy(),
        )
        rt._record_search_view(
            artifact_id=ARTIFACT_ID, version=1, content="x", now_tick=1,
        )
        # No exception, no side effects

    def test_json_serializable(self):
        log: list[dict] = []
        rt = _audit_runtime(log)
        rt._record_search_view(
            artifact_id=ARTIFACT_ID, version=1, content="hello", now_tick=1,
        )
        roundtrip = json.loads(json.dumps(log[0]))
        assert roundtrip == log[0]


# ---------------------------------------------------------------------------
# Unit 3: Wired delivery paths
# ---------------------------------------------------------------------------


class TestWiredCacheHit:
    def test_cache_hit_emits_audit(self):
        log: list[dict] = []
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt = _audit_runtime(log, coordinator=coordinator)
        rt.read(artifact.id, now_tick=1)  # fetch
        log.clear()
        rt.read(artifact.id, now_tick=2)  # cache hit
        assert len(log) == 1
        assert log[0]["source"] == "cache_hit"
        assert log[0]["tick"] == 2


class TestWiredFetch:
    def test_fetch_emits_audit(self):
        log: list[dict] = []
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt = _audit_runtime(log, coordinator=coordinator)
        rt.read(artifact.id, now_tick=1)
        assert len(log) == 1
        assert log[0]["source"] == "fetch"
        assert log[0]["tick"] == 1
        assert log[0]["version"] == 1


class TestWiredBroadcast:
    def test_broadcast_emits_audit(self):
        log: list[dict] = []
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt = _audit_runtime(log, coordinator=coordinator)
        rt.handle_update(
            artifact_id=artifact.id, version=2, content="v2", now_tick=5,
        )
        assert len(log) == 1
        assert log[0]["source"] == "broadcast"
        assert log[0]["tick"] == 5
        assert log[0]["version"] == 2


class TestWiredWrite:
    def test_write_emits_audit(self):
        log: list[dict] = []
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt = _audit_runtime(log, coordinator=coordinator)
        rt.read(artifact.id, now_tick=1)
        log.clear()
        rt.write(artifact.id, content="v2", now_tick=2)
        write_records = [e for e in log if e["source"] == "write"]
        assert len(write_records) == 1
        assert write_records[0]["version"] == 2

    def test_write_valid_hash_succeeds(self):
        log: list[dict] = []
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt = _audit_runtime(log, coordinator=coordinator)
        rt.read(artifact.id, now_tick=1)
        correct_hash = compute_content_hash("v2")
        rt.write(artifact.id, content="v2", now_tick=2, content_hash=correct_hash)

    def test_write_mismatched_hash_raises(self):
        log: list[dict] = []
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt = _audit_runtime(log, coordinator=coordinator)
        rt.read(artifact.id, now_tick=1)
        with pytest.raises(ValueError, match="content_hash mismatch"):
            rt.write(artifact.id, content="v2", now_tick=2, content_hash="wrong")


class TestEndToEndAuditCycle:
    def test_read_write_broadcast_sequence(self):
        log: list[dict] = []
        seq = [0]
        coordinator = CoordinatorService(ArtifactRegistry())
        artifact = coordinator.register_artifact(name="doc", content="v1")
        rt_a = _audit_runtime(log, coordinator=coordinator, agent_id=uuid4(), audit_seq=seq)
        rt_b = _audit_runtime(log, coordinator=coordinator, agent_id=uuid4(), audit_seq=seq)

        rt_a.read(artifact.id, now_tick=1)  # fetch
        rt_b.read(artifact.id, now_tick=1)  # fetch
        rt_a.read(artifact.id, now_tick=2)  # cache hit
        rt_b.handle_update(artifact_id=artifact.id, version=2, content="v2", now_tick=3)

        sources = [e["source"] for e in log]
        assert "fetch" in sources
        assert "cache_hit" in sources
        assert "broadcast" in sources
        seq_nums = [e["sequence_number"] for e in log]
        assert seq_nums == sorted(seq_nums)
        assert len(set(seq_nums)) == len(seq_nums)  # no duplicates
