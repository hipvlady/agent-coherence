"""In-memory artifact registry for coherence coordination."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from ccs.core.states import MESIState, TransientState
from ccs.core.types import Artifact


@dataclass
class ArtifactRecord:
    """Internal registry record for one artifact."""

    artifact: Artifact
    content: str
    state_by_agent: dict[UUID, MESIState] = field(default_factory=dict)
    transient_by_agent: dict[UUID, TransientState] = field(default_factory=dict)
    transient_tick_by_agent: dict[UUID, int] = field(default_factory=dict)
    last_writer: Optional[UUID] = None


class ArtifactRegistry:
    """Canonical in-memory artifact directory and payload store."""

    def __init__(self) -> None:
        self._records: dict[UUID, ArtifactRecord] = {}

    def register_artifact(self, artifact: Artifact, content: str) -> None:
        """Insert artifact record into registry."""
        self._records[artifact.id] = ArtifactRecord(artifact=artifact, content=content)

    def has_artifact(self, artifact_id: UUID) -> bool:
        """Return whether an artifact exists in registry."""
        return artifact_id in self._records

    def artifact_ids(self) -> list[UUID]:
        """Return all known artifact ids."""
        return list(self._records.keys())

    def get_artifact(self, artifact_id: UUID) -> Optional[Artifact]:
        """Return artifact metadata if present."""
        record = self._records.get(artifact_id)
        return record.artifact if record else None

    def get_content(self, artifact_id: UUID) -> Optional[str]:
        """Return artifact content if present."""
        record = self._records.get(artifact_id)
        return record.content if record else None

    def set_artifact_and_content(
        self,
        artifact_id: UUID,
        artifact: Artifact,
        content: str,
        *,
        last_writer: Optional[UUID] = None,
    ) -> None:
        """Replace artifact metadata/content for an existing record."""
        self._records[artifact_id].artifact = artifact
        self._records[artifact_id].content = content
        self._records[artifact_id].last_writer = last_writer

    def get_state_map(self, artifact_id: UUID) -> dict[UUID, MESIState]:
        """Return copy of per-agent MESI states for an artifact."""
        return dict(self._records[artifact_id].state_by_agent)

    def get_agent_state(self, artifact_id: UUID, agent_id: UUID) -> MESIState | None:
        """Return MESI state for one agent/artifact pair if present."""
        return self._records[artifact_id].state_by_agent.get(agent_id)

    def set_agent_state(self, artifact_id: UUID, agent_id: UUID, state: MESIState) -> None:
        """Set MESI state for one agent/artifact pair."""
        self._records[artifact_id].state_by_agent[agent_id] = state

    def get_agent_transient(self, artifact_id: UUID, agent_id: UUID) -> TransientState | None:
        """Return transient state for one agent/artifact pair if present."""
        return self._records[artifact_id].transient_by_agent.get(agent_id)

    def set_agent_transient(
        self,
        artifact_id: UUID,
        agent_id: UUID,
        transient_state: TransientState,
        *,
        entered_tick: int,
    ) -> None:
        """Set transient state and entry tick for one agent/artifact pair."""
        self._records[artifact_id].transient_by_agent[agent_id] = transient_state
        self._records[artifact_id].transient_tick_by_agent[agent_id] = entered_tick

    def clear_agent_transient(self, artifact_id: UUID, agent_id: UUID) -> None:
        """Clear transient state and timestamp for one agent/artifact pair."""
        self._records[artifact_id].transient_by_agent.pop(agent_id, None)
        self._records[artifact_id].transient_tick_by_agent.pop(agent_id, None)

    def get_transient_map(self, artifact_id: UUID) -> dict[UUID, TransientState]:
        """Return copy of per-agent transient states for an artifact."""
        return dict(self._records[artifact_id].transient_by_agent)

    def get_transient_tick(self, artifact_id: UUID, agent_id: UUID) -> int | None:
        """Return tick when agent entered transient state if present."""
        return self._records[artifact_id].transient_tick_by_agent.get(agent_id)

    def valid_holders(self, artifact_id: UUID) -> list[UUID]:
        """Return agents that currently hold non-invalid entries."""
        return [
            agent_id
            for agent_id, state in self._records[artifact_id].state_by_agent.items()
            if state != MESIState.INVALID
        ]
