"""Unit tests for multi-run aggregation helpers."""

from __future__ import annotations

from ccs.simulation.aggregation import aggregate_comparison_runs, aggregate_strategy_runs, flatten_metrics
from ccs.simulation.metrics import SimulationMetrics


def _metric(strategy: str, unauthorized: int, depth0: int) -> SimulationMetrics:
    return SimulationMetrics(
        scenario="tiny",
        strategy=strategy,
        total_ticks=10,
        total_actions=10,
        unauthorized_actions_count=unauthorized,
        unauthorized_actions_by_depth={0: depth0},
        revocation_latency_p50=1.0,
        revocation_latency_p99=2.0,
        staleness_window_max=3,
        convergence_time=4.0,
        message_overhead=5,
        revalidation_count=6,
        transient_state_timeouts=7,
    )


def test_aggregate_strategy_runs() -> None:
    runs = [_metric("lazy", unauthorized=2, depth0=2), _metric("lazy", unauthorized=4, depth0=4)]
    agg = aggregate_strategy_runs("lazy", runs)

    assert agg.strategy == "lazy"
    assert agg.runs == 2
    assert agg.unauthorized_mean == 3.0
    assert agg.p50_mean == 1.0
    assert agg.unauthorized_by_depth_mean[0] == 3.0


def test_aggregate_comparison_and_flatten() -> None:
    grouped = {
        "eager": [_metric("eager", unauthorized=1, depth0=1)],
        "lazy": [_metric("lazy", unauthorized=3, depth0=3), _metric("lazy", unauthorized=5, depth0=5)],
    }

    flattened = flatten_metrics(grouped)
    assert len(flattened) == 3

    aggregated = aggregate_comparison_runs(grouped)
    assert [a.strategy for a in aggregated] == ["eager", "lazy"]
    assert aggregated[0].unauthorized_mean == 1.0
    assert aggregated[1].unauthorized_mean == 4.0

