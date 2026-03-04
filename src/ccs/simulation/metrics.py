"""Simulation metrics dataclasses used by aggregation and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimulationMetrics:
    """Single-run metrics payload for one strategy and scenario."""

    scenario: str
    strategy: str
    total_ticks: int
    total_actions: int
    unauthorized_actions_count: int
    unauthorized_actions_by_depth: dict[int, int]
    revocation_latency_p50: float = 0.0
    revocation_latency_p99: float = 0.0
    staleness_window_max: int = 0
    convergence_time: float = 0.0
    message_overhead: int = 0
    revalidation_count: int = 0
    transient_state_timeouts: int = 0
    bound_violations_by_depth: dict[int, int] = field(default_factory=dict)

