# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""In-memory artifact registry for coherence coordination."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from ccs.core.states import MESIState, TransientState
from ccs.core.types import Artifact

CCS_STATE_LOG_SCHEMA_VERSION = "ccs.state_log.v2"


@dataclass
class ArtifactRecord:
    """Internal registry record for one artifact."""

    artifact: Artifact
    content: str
    state_by_agent: dict[UUID, MESIState] = field(default_factory=dict)
    transient_by_agent: dict[UUID, TransientState] = field(default_factory=dict)
    transient_tick_by_agent: dict[UUID, int] = field(default_factory=dict)
    last_writer: Optional[UUID] = None
    version_history: dict[int, str] = field(default_factory=dict)


class ArtifactRegistry:
    """Canonical in-memory artifact directory and payload store."""

    def __init__(
        self,
        *,
        state_log: Callable[[dict[str, Any]], None] | None = None,
        agent_names: dict[UUID, str] | None = None,
        instance_id: str | None = None,
        retain_versions: bool = False,
    ) -> None:
        if state_log is not None and instance_id is None:
            raise ValueError(
                "instance_id must be provided when state_log is set; "
                "pass instance_id=str(uuid4()) or route through CCSStore which manages it automatically"
            )
        self._records: dict[UUID, ArtifactRecord] = {}
        self._state_log = state_log
        self._agent_names = agent_names
        self._instance_id: str = instance_id if instance_id is not None else str(uuid4())
        self._seq: int = 0
        self._retain_versions = retain_versions

    def register_artifact(self, artifact: Artifact, content: str) -> None:
        """Insert artifact record into registry."""
        record = ArtifactRecord(artifact=artifact, content=content)
        if self._retain_versions:
            record.version_history[artifact.version] = content
        self._records[artifact.id] = record

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
        if self._retain_versions:
            self._records[artifact_id].version_history[artifact.version] = content
        self._records[artifact_id].artifact = artifact
        self._records[artifact_id].content = content
        self._records[artifact_id].last_writer = last_writer

    def get_content_at_version(self, artifact_id: UUID, version: int) -> str | None:
        """Return content for a specific version, if retained."""
        record = self._records.get(artifact_id)
        if record is None:
            return None
        return record.version_history.get(version)

    def get_state_map(self, artifact_id: UUID) -> dict[UUID, MESIState]:
        """Return copy of per-agent MESI states for an artifact."""
        return dict(self._records[artifact_id].state_by_agent)

    def get_agent_state(self, artifact_id: UUID, agent_id: UUID) -> MESIState | None:
        """Return MESI state for one agent/artifact pair if present."""
        return self._records[artifact_id].state_by_agent.get(agent_id)

    def set_agent_state(
        self,
        artifact_id: UUID,
        agent_id: UUID,
        state: MESIState,
        *,
        trigger: str = "unknown",
        tick: int = 0,
        content_hash: str | None = None,
    ) -> None:
        """Set MESI state for one agent/artifact pair."""
        from_state = self._records[artifact_id].state_by_agent.get(agent_id, MESIState.INVALID)
        self._records[artifact_id].state_by_agent[agent_id] = state
        if self._state_log is not None:
            self._seq += 1
            entry = {
                "tick": tick,
                "artifact_id": str(artifact_id),
                "agent_id": str(agent_id),
                "agent_name": self._agent_names.get(agent_id) if self._agent_names is not None else None,
                "from_state": from_state.name,
                "to_state": state.name,
                "trigger": trigger,
                "version": self._records[artifact_id].artifact.version,
                "content_hash": content_hash,
                "sequence_number": self._seq,
                "instance_id": self._instance_id,
                "schema_version": CCS_STATE_LOG_SCHEMA_VERSION,
            }
            try:
                self._state_log(entry)
            except Exception:
                # Sequence number is reserved on success, not on attempt.
                # Roll back so the next successful emission does not create a phantom gap.
                self._seq -= 1
                raise

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

    def remove_artifact(self, artifact_id: UUID) -> None:
        """Remove artifact record and all associated state from registry."""
        self._records.pop(artifact_id, None)

    def valid_holders(self, artifact_id: UUID) -> list[UUID]:
        """Return agents that currently hold non-invalid entries."""
        return [
            agent_id
            for agent_id, state in self._records[artifact_id].state_by_agent.items()
            if state != MESIState.INVALID
        ]
