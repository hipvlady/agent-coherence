"""Agent runtime encapsulating read/write/invalidation protocol flows."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from ccs.coordinator.service import CoordinatorService
from ccs.core.states import MESIState
from ccs.core.types import Artifact, FetchRequest, FetchResponse, InvalidationSignal
from ccs.strategies.base import SyncStrategy

from .cache import ArtifactCache


class AgentRuntime:
    """Reusable protocol participant for one agent identity."""

    def __init__(
        self,
        *,
        agent_id: UUID,
        coordinator: CoordinatorService,
        strategy: SyncStrategy,
        cache: Optional[ArtifactCache] = None,
    ) -> None:
        self.agent_id = agent_id
        self.coordinator = coordinator
        self.strategy = strategy
        self.cache = cache if cache is not None else ArtifactCache()
        self._content_by_artifact: dict[UUID, str] = {}

    def read(self, artifact_id: UUID, *, now_tick: int) -> FetchResponse:
        """Return artifact view from cache or coordinator."""
        entry = self.cache.get(artifact_id)
        if entry is None or self.strategy.requires_refresh(entry, now_tick=now_tick):
            return self._fetch(artifact_id, now_tick=now_tick)

        touched = self.strategy.on_read(entry, now_tick=now_tick)
        self.cache.put(artifact_id, touched)
        return FetchResponse(
            artifact_id=artifact_id,
            version=touched.local_version,
            content=self._content_by_artifact.get(artifact_id, ""),
            state_grant=touched.state,
        )

    def write(
        self,
        artifact_id: UUID,
        *,
        content: str,
        now_tick: int,
        content_hash: str | None = None,
        size_tokens: int | None = None,
    ) -> tuple[Artifact, list[InvalidationSignal]]:
        """Write new artifact content through coordinator protocol."""
        entry = self.cache.get(artifact_id)
        if entry is None or self.strategy.requires_refresh(entry, now_tick=now_tick):
            self._fetch(artifact_id, now_tick=now_tick)

        write_signals = self.coordinator.write(
            agent_id=self.agent_id,
            artifact_id=artifact_id,
            issued_at_tick=now_tick,
        )
        updated, commit_signals = self.coordinator.commit(
            agent_id=self.agent_id,
            artifact_id=artifact_id,
            content=content,
            issued_at_tick=now_tick,
            content_hash=content_hash,
            size_tokens=size_tokens,
        )
        self.cache.put(
            artifact_id,
            self.strategy.on_fetch(
                artifact_id=artifact_id,
                version=updated.version,
                state=MESIState.MODIFIED,
                now_tick=now_tick,
            ),
        )
        self._content_by_artifact[artifact_id] = content
        return updated, [*write_signals, *commit_signals]

    def handle_invalidation(self, signal: InvalidationSignal) -> None:
        """Apply invalidation event from coordinator/event bus."""
        self.cache.invalidate(
            signal.artifact_id,
            invalidated_version=max(signal.new_version - 1, 0),
            issued_at_tick=signal.issued_at_tick,
        )
        self.coordinator.invalidate(
            agent_id=self.agent_id,
            artifact_id=signal.artifact_id,
            new_version=signal.new_version,
            issuer_agent_id=signal.issuer_agent_id,
            issued_at_tick=signal.issued_at_tick,
        )

    def handle_update(
        self,
        *,
        artifact_id: UUID,
        version: int,
        content: str,
        now_tick: int,
        writer_agent_id: UUID | None = None,
    ) -> None:
        """Apply eager-broadcast content update from peer/coordinator."""
        self.cache.put(
            artifact_id,
            self.strategy.on_fetch(
                artifact_id=artifact_id,
                version=version,
                state=MESIState.SHARED,
                now_tick=now_tick,
            ),
        )
        self._content_by_artifact[artifact_id] = content
        self.coordinator.registry.set_agent_state(artifact_id, self.agent_id, MESIState.SHARED)
        if writer_agent_id is not None:
            self.coordinator.registry.set_agent_state(artifact_id, writer_agent_id, MESIState.SHARED)

    def content(self, artifact_id: UUID) -> str | None:
        """Return locally cached content body for artifact if present."""
        return self._content_by_artifact.get(artifact_id)

    def _fetch(self, artifact_id: UUID, *, now_tick: int) -> FetchResponse:
        response = self.coordinator.fetch(
            FetchRequest(
                artifact_id=artifact_id,
                requesting_agent_id=self.agent_id,
                requested_at_tick=now_tick,
            )
        )
        self.cache.put(
            artifact_id,
            self.strategy.on_fetch(
                artifact_id=artifact_id,
                version=response.version,
                state=response.state_grant,
                now_tick=now_tick,
            ),
        )
        self._content_by_artifact[artifact_id] = response.content
        return response
