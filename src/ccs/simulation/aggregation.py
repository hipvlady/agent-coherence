"""Aggregation utilities for multi-run strategy comparisons."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from .metrics import SimulationMetrics


def _mean(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return statistics.pstdev(values)


@dataclass(frozen=True)
class AggregatedMetrics:
    """Aggregated per-strategy values across repeated runs."""

    strategy: str
    runs: int
    unauthorized_mean: float
    unauthorized_std: float
    p50_mean: float
    p50_std: float
    p99_mean: float
    p99_std: float
    staleness_max_mean: float
    staleness_max_std: float
    convergence_mean: float
    convergence_std: float
    message_overhead_mean: float
    message_overhead_std: float
    revalidations_mean: float
    revalidations_std: float
    transient_timeouts_mean: float
    transient_timeouts_std: float
    unauthorized_by_depth_mean: dict[int, float]
    unauthorized_by_depth_std: dict[int, float]


def aggregate_strategy_runs(strategy: str, runs: Sequence[SimulationMetrics]) -> AggregatedMetrics:
    """Aggregate one strategy across repeated simulation runs."""
    depth_values: dict[int, list[float]] = {}
    for metrics in runs:
        for depth in metrics.unauthorized_actions_by_depth.keys():
            depth_values.setdefault(depth, [])
    for depth in depth_values:
        for metrics in runs:
            depth_values[depth].append(float(metrics.unauthorized_actions_by_depth.get(depth, 0)))

    return AggregatedMetrics(
        strategy=strategy,
        runs=len(runs),
        unauthorized_mean=_mean([float(m.unauthorized_actions_count) for m in runs]),
        unauthorized_std=_std([float(m.unauthorized_actions_count) for m in runs]),
        p50_mean=_mean([m.revocation_latency_p50 for m in runs]),
        p50_std=_std([m.revocation_latency_p50 for m in runs]),
        p99_mean=_mean([m.revocation_latency_p99 for m in runs]),
        p99_std=_std([m.revocation_latency_p99 for m in runs]),
        staleness_max_mean=_mean([float(m.staleness_window_max) for m in runs]),
        staleness_max_std=_std([float(m.staleness_window_max) for m in runs]),
        convergence_mean=_mean([m.convergence_time for m in runs]),
        convergence_std=_std([m.convergence_time for m in runs]),
        message_overhead_mean=_mean([float(m.message_overhead) for m in runs]),
        message_overhead_std=_std([float(m.message_overhead) for m in runs]),
        revalidations_mean=_mean([float(m.revalidation_count) for m in runs]),
        revalidations_std=_std([float(m.revalidation_count) for m in runs]),
        transient_timeouts_mean=_mean([float(m.transient_state_timeouts) for m in runs]),
        transient_timeouts_std=_std([float(m.transient_state_timeouts) for m in runs]),
        unauthorized_by_depth_mean={depth: _mean(values) for depth, values in depth_values.items()},
        unauthorized_by_depth_std={depth: _std(values) for depth, values in depth_values.items()},
    )


def aggregate_comparison_runs(
    metrics_by_strategy: dict[str, Sequence[SimulationMetrics]],
) -> list[AggregatedMetrics]:
    """Aggregate all strategies preserving input order."""
    aggregated: list[AggregatedMetrics] = []
    for strategy, runs in metrics_by_strategy.items():
        aggregated.append(aggregate_strategy_runs(strategy, runs))
    return aggregated


def flatten_metrics(metrics_by_strategy: dict[str, Iterable[SimulationMetrics]]) -> list[SimulationMetrics]:
    """Flatten grouped strategy metrics into one ordered list."""
    flattened: list[SimulationMetrics] = []
    for runs in metrics_by_strategy.values():
        flattened.extend(list(runs))
    return flattened

