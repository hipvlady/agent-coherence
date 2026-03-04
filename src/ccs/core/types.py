"""Core domain dataclasses for artifact coherence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4

from .states import MESIState, TransientState


@dataclass(frozen=True)
class Artifact:
    """Named shared artifact tracked by the coherence coordinator."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    version: int = 0
    content_hash: Optional[str] = None
    size_tokens: Optional[int] = None
    depends_on: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ArtifactCacheEntry:
    """Per-agent cached view of one artifact."""

    artifact_id: UUID
    state: MESIState
    local_version: int
    access_count: int = 0
    acquired_at_tick: int = 0
    expires_at_tick: Optional[int] = None
    transient_state: Optional[TransientState] = None
    transient_entered_tick: Optional[int] = None


@dataclass(frozen=True)
class InvalidationSignal:
    """Lightweight invalidation signal sent to agents."""

    artifact_id: UUID
    new_version: int
    issued_at_tick: int
    issuer_agent_id: UUID


@dataclass(frozen=True)
class FetchRequest:
    """Request to fetch canonical artifact content/version."""

    artifact_id: UUID
    requesting_agent_id: UUID
    requested_at_tick: int


@dataclass(frozen=True)
class FetchResponse:
    """Fetch response containing granted state and content payload."""

    artifact_id: UUID
    version: int
    content: str
    state_grant: MESIState

