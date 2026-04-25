# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Framework-facing integration adapters for CCS runtime."""

from .autogen import AutoGenAdapter
from .base import CoherenceAdapterCore
from .ccsstore import CCSStore, StoreMetricEvent
from .crewai import CrewAIAdapter
from .langgraph import LangGraphAdapter

__all__ = [
    "CCSStore",
    "CoherenceAdapterCore",
    "LangGraphAdapter",
    "CrewAIAdapter",
    "AutoGenAdapter",
    "StoreMetricEvent",
]
