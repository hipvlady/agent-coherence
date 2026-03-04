"""Tests for agent local cache behavior."""

from __future__ import annotations

from uuid import uuid4

from ccs.agent.cache import ArtifactCache
from ccs.core.states import MESIState
from ccs.core.types import ArtifactCacheEntry


def test_cache_get_put_and_has_valid() -> None:
    cache = ArtifactCache()
    artifact_id = uuid4()
    assert cache.get(artifact_id) is None
    assert cache.has_valid(artifact_id) is False

    entry = ArtifactCacheEntry(
        artifact_id=artifact_id,
        state=MESIState.SHARED,
        local_version=3,
    )
    cache.put(artifact_id, entry)
    assert cache.get(artifact_id) == entry
    assert cache.has_valid(artifact_id) is True


def test_invalidate_existing_entry() -> None:
    cache = ArtifactCache()
    artifact_id = uuid4()
    cache.put(
        artifact_id,
        ArtifactCacheEntry(
            artifact_id=artifact_id,
            state=MESIState.EXCLUSIVE,
            local_version=7,
        ),
    )

    cache.invalidate(artifact_id, invalidated_version=5, issued_at_tick=10)
    invalid = cache.get(artifact_id)
    assert invalid is not None
    assert invalid.state == MESIState.INVALID
    assert invalid.local_version == 5
    assert cache.has_valid(artifact_id) is False


def test_invalidate_missing_entry_creates_placeholder() -> None:
    cache = ArtifactCache()
    artifact_id = uuid4()
    cache.invalidate(artifact_id, invalidated_version=2, issued_at_tick=4)

    invalid = cache.get(artifact_id)
    assert invalid is not None
    assert invalid.state == MESIState.INVALID
    assert invalid.local_version == 2
    assert invalid.acquired_at_tick == 4
