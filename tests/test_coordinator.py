"""Contract tests for coordinator registry/service operations."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ccs.coordinator.registry import ArtifactRegistry
from ccs.coordinator.service import CoordinatorService
from ccs.core.exceptions import CoherenceError
from ccs.core.states import MESIState
from ccs.core.types import FetchRequest


def _service() -> CoordinatorService:
    return CoordinatorService(ArtifactRegistry())


def test_fetch_first_holder_gets_exclusive() -> None:
    svc = _service()
    artifact = svc.register_artifact(name="plan.md", content="v1")
    agent_a = uuid4()

    resp = svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=agent_a, requested_at_tick=1))

    assert resp.state_grant == MESIState.EXCLUSIVE
    assert resp.version == 1
    assert svc.registry.get_agent_state(artifact.id, agent_a) == MESIState.EXCLUSIVE


def test_second_fetch_downgrades_existing_owner_to_shared() -> None:
    svc = _service()
    artifact = svc.register_artifact(name="plan.md", content="v1")
    agent_a = uuid4()
    agent_b = uuid4()

    svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=agent_a, requested_at_tick=1))
    resp_b = svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=agent_b, requested_at_tick=2))

    assert resp_b.state_grant == MESIState.SHARED
    assert svc.registry.get_agent_state(artifact.id, agent_a) == MESIState.SHARED
    assert svc.registry.get_agent_state(artifact.id, agent_b) == MESIState.SHARED


def test_write_invalidates_peers_and_grants_exclusive() -> None:
    svc = _service()
    artifact = svc.register_artifact(name="plan.md", content="v1")
    agent_a = uuid4()
    agent_b = uuid4()
    svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=agent_a, requested_at_tick=1))
    svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=agent_b, requested_at_tick=2))

    signals = svc.write(agent_id=agent_a, artifact_id=artifact.id)

    assert len(signals) == 1
    assert signals[0].issuer_agent_id == agent_a
    assert svc.registry.get_agent_state(artifact.id, agent_a) == MESIState.EXCLUSIVE
    assert svc.registry.get_agent_state(artifact.id, agent_b) == MESIState.INVALID


def test_commit_requires_owner_state() -> None:
    svc = _service()
    artifact = svc.register_artifact(name="plan.md", content="v1")
    non_owner = uuid4()
    with pytest.raises(CoherenceError):
        svc.commit(agent_id=non_owner, artifact_id=artifact.id, content="v2")


def test_commit_increments_version_monotonically() -> None:
    svc = _service()
    owner = uuid4()
    peer = uuid4()
    artifact = svc.register_artifact(name="plan.md", content="v1")
    svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=owner, requested_at_tick=1))
    svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=peer, requested_at_tick=2))
    svc.write(agent_id=owner, artifact_id=artifact.id)

    v2, _ = svc.commit(agent_id=owner, artifact_id=artifact.id, content="v2")
    svc.write(agent_id=owner, artifact_id=artifact.id)
    v3, _ = svc.commit(agent_id=owner, artifact_id=artifact.id, content="v3")

    assert v2.version == 2
    assert v3.version == 3
    assert svc.registry.get_agent_state(artifact.id, owner) == MESIState.MODIFIED
    assert svc.registry.get_agent_state(artifact.id, peer) == MESIState.INVALID


def test_invalidate_marks_agent_invalid() -> None:
    svc = _service()
    artifact = svc.register_artifact(name="plan.md", content="v1")
    agent = uuid4()
    svc.fetch(FetchRequest(artifact_id=artifact.id, requesting_agent_id=agent, requested_at_tick=1))
    signal = svc.invalidate(
        agent_id=agent,
        artifact_id=artifact.id,
        new_version=2,
        issuer_agent_id=uuid4(),
        issued_at_tick=10,
    )

    assert signal.new_version == 2
    assert svc.registry.get_agent_state(artifact.id, agent) == MESIState.INVALID

