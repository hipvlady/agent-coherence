"""Coordinator service implementing core artifact coherence operations."""

from __future__ import annotations

from uuid import UUID

from ccs.core.exceptions import CoherenceError
from ccs.core.invariants import check_monotonic_version, check_single_writer
from ccs.core.states import MESIState
from ccs.core.types import Artifact, FetchRequest, FetchResponse, InvalidationSignal

from .registry import ArtifactRegistry


class CoordinatorService:
    """Control-plane service for artifact read/write/commit synchronization."""

    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def register_artifact(
        self,
        *,
        name: str,
        content: str,
        initial_owner: UUID | None = None,
        size_tokens: int | None = None,
        content_hash: str | None = None,
        depends_on: tuple[UUID, ...] = (),
    ) -> Artifact:
        """Register a new artifact and optionally assign an initial owner."""
        artifact = Artifact(
            name=name,
            version=1,
            content_hash=content_hash,
            size_tokens=size_tokens,
            depends_on=depends_on,
        )
        self.registry.register_artifact(artifact, content)
        if initial_owner is not None:
            self.registry.set_agent_state(artifact.id, initial_owner, MESIState.EXCLUSIVE)
        return artifact

    def fetch(self, request: FetchRequest) -> FetchResponse:
        """Fetch canonical artifact payload and grant requester state."""
        artifact = self._require_artifact(request.artifact_id)
        content = self.registry.get_content(request.artifact_id)
        assert content is not None

        state_map = self.registry.get_state_map(request.artifact_id)
        other_holders = [
            agent_id
            for agent_id, state in state_map.items()
            if agent_id != request.requesting_agent_id and state != MESIState.INVALID
        ]

        grant = MESIState.EXCLUSIVE if not other_holders else MESIState.SHARED
        if other_holders:
            # Multiple readers must stay coherent; downgrade any exclusive/modified holder.
            for agent_id in other_holders:
                self.registry.set_agent_state(request.artifact_id, agent_id, MESIState.SHARED)

        self.registry.set_agent_state(request.artifact_id, request.requesting_agent_id, grant)
        self._validate_single_writer(request.artifact_id)

        return FetchResponse(
            artifact_id=request.artifact_id,
            version=artifact.version,
            content=content,
            state_grant=grant,
        )

    def write(self, *, agent_id: UUID, artifact_id: UUID) -> list[InvalidationSignal]:
        """Request write ownership by invalidating peers and granting EXCLUSIVE."""
        artifact = self._require_artifact(artifact_id)
        signals: list[InvalidationSignal] = []
        for peer_id, state in self.registry.get_state_map(artifact_id).items():
            if peer_id == agent_id or state == MESIState.INVALID:
                continue
            self.registry.set_agent_state(artifact_id, peer_id, MESIState.INVALID)
            signals.append(
                InvalidationSignal(
                    artifact_id=artifact_id,
                    new_version=artifact.version,
                    issued_at_tick=0,
                    issuer_agent_id=agent_id,
                )
            )

        self.registry.set_agent_state(artifact_id, agent_id, MESIState.EXCLUSIVE)
        self._validate_single_writer(artifact_id)
        return signals

    def upgrade(self, *, agent_id: UUID, artifact_id: UUID) -> list[InvalidationSignal]:
        """Upgrade a shared holder to exclusive owner (alias of write request)."""
        return self.write(agent_id=agent_id, artifact_id=artifact_id)

    def commit(
        self,
        *,
        agent_id: UUID,
        artifact_id: UUID,
        content: str,
        content_hash: str | None = None,
        size_tokens: int | None = None,
    ) -> tuple[Artifact, list[InvalidationSignal]]:
        """Commit modified content, increment version, and invalidate peers."""
        artifact = self._require_artifact(artifact_id)
        agent_state = self.registry.get_agent_state(artifact_id, agent_id)
        if agent_state not in {MESIState.EXCLUSIVE, MESIState.MODIFIED}:
            raise CoherenceError(
                f"commit_not_allowed agent={agent_id} artifact={artifact_id} state={agent_state}"
            )

        next_version = artifact.version + 1
        check_monotonic_version(artifact.version, next_version)
        updated = Artifact(
            id=artifact.id,
            name=artifact.name,
            version=next_version,
            content_hash=content_hash if content_hash is not None else artifact.content_hash,
            size_tokens=size_tokens if size_tokens is not None else artifact.size_tokens,
            depends_on=artifact.depends_on,
        )
        self.registry.set_artifact_and_content(
            artifact_id,
            updated,
            content,
            last_writer=agent_id,
        )

        signals: list[InvalidationSignal] = []
        for peer_id, state in self.registry.get_state_map(artifact_id).items():
            if peer_id == agent_id or state == MESIState.INVALID:
                continue
            self.registry.set_agent_state(artifact_id, peer_id, MESIState.INVALID)
            signals.append(
                InvalidationSignal(
                    artifact_id=artifact_id,
                    new_version=next_version,
                    issued_at_tick=0,
                    issuer_agent_id=agent_id,
                )
            )
        self.registry.set_agent_state(artifact_id, agent_id, MESIState.MODIFIED)
        self._validate_single_writer(artifact_id)
        return updated, signals

    def invalidate(
        self,
        *,
        agent_id: UUID,
        artifact_id: UUID,
        new_version: int,
        issuer_agent_id: UUID,
        issued_at_tick: int,
    ) -> InvalidationSignal:
        """Apply invalidation for one agent and return corresponding signal object."""
        self._require_artifact(artifact_id)
        self.registry.set_agent_state(artifact_id, agent_id, MESIState.INVALID)
        return InvalidationSignal(
            artifact_id=artifact_id,
            new_version=new_version,
            issued_at_tick=issued_at_tick,
            issuer_agent_id=issuer_agent_id,
        )

    def _validate_single_writer(self, artifact_id: UUID) -> None:
        check_single_writer(self.registry.get_state_map(artifact_id))

    def _require_artifact(self, artifact_id: UUID) -> Artifact:
        artifact = self.registry.get_artifact(artifact_id)
        if artifact is None:
            raise CoherenceError(f"artifact_not_found artifact={artifact_id}")
        return artifact

