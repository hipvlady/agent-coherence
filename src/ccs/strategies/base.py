# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Base strategy contract for synchronization policy decisions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from uuid import UUID

from ccs.core.states import MESIState
from ccs.core.types import ArtifactCacheEntry


class SyncStrategy(ABC):
    """Interface for policy-specific cache refresh and propagation rules."""

    name: str

    def invalidates_peers_on_commit(self) -> bool:
        """Whether peers should receive invalidation when writer commits."""
        return True

    def broadcasts_content_on_commit(self) -> bool:
        """Whether the strategy pushes full content on commit."""
        return False

    def staleness_bound(self) -> int | None:
        """Max stale steps permitted by strategy; None means unbounded by strategy."""
        return None

    @abstractmethod
    def requires_refresh(self, entry: ArtifactCacheEntry, *, now_tick: int) -> bool:
        """Return whether runtime must fetch before local read."""

    @abstractmethod
    def on_read(self, entry: ArtifactCacheEntry, *, now_tick: int) -> ArtifactCacheEntry:
        """Return updated cache entry after local read access."""

    @abstractmethod
    def on_fetch(
        self,
        *,
        artifact_id: UUID,
        version: int,
        state: MESIState,
        now_tick: int,
    ) -> ArtifactCacheEntry:
        """Return refreshed cache entry after coordinator fetch."""

    def _new_entry(
        self,
        *,
        artifact_id: UUID,
        version: int,
        state: MESIState,
        now_tick: int,
    ) -> ArtifactCacheEntry:
        return ArtifactCacheEntry(
            artifact_id=artifact_id,
            state=state,
            local_version=version,
            access_count=0,
            acquired_at_tick=now_tick,
            expires_at_tick=None,
            transient_state=None,
            transient_entered_tick=None,
        )

    def _touch(self, entry: ArtifactCacheEntry) -> ArtifactCacheEntry:
        """Increment local access counter for telemetry and policy checks."""
        return replace(entry, access_count=entry.access_count + 1)
