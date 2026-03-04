"""Unit tests for multi-run coherence aggregation helpers."""

from __future__ import annotations

from ccs.simulation.aggregation import aggregate_comparison_runs, aggregate_strategy_runs, flatten_metrics
from ccs.simulation.metrics import SimulationMetrics


def _metric(strategy: str, *, fetch: int, broadcast: int, stale_reads: int) -> SimulationMetrics:
    return SimulationMetrics(
        scenario="tiny",
        strategy=strategy,
        seed=1,
        duration_ticks=10,
        agent_count=2,
        artifact_count=1,
        total_actions=10,
        read_actions=8,
        write_actions=2,
        fetch_actions=3,
        cache_hits=5,
        cache_misses=3,
        stale_reads=stale_reads,
        max_stale_steps=stale_reads,
        staleness_bound_violations=0,
        swmr_violations=0,
        monotonic_version_violations=0,
        invalidations_issued=2,
        invalidations_delivered=2,
        updates_issued=0,
        updates_delivered=0,
        message_overhead=2,
        tokens_fetch=fetch,
        tokens_broadcast=broadcast,
        tokens_invalidation=24,
        context_injections=3,
        transient_state_timeouts=0,
    )


def test_aggregate_strategy_runs() -> None:
    runs = [
        _metric("lazy", fetch=100, broadcast=0, stale_reads=1),
        _metric("lazy", fetch=300, broadcast=0, stale_reads=3),
    ]
    agg = aggregate_strategy_runs("lazy", runs)

    assert agg.strategy == "lazy"
    assert agg.runs == 2
    assert agg.fetch_tokens_mean == 200.0
    assert agg.broadcast_tokens_mean == 0.0
    assert agg.stale_reads_mean == 2.0


def test_aggregate_comparison_and_flatten() -> None:
    grouped = {
        "eager": [_metric("eager", fetch=50, broadcast=200, stale_reads=0)],
        "lazy": [
            _metric("lazy", fetch=120, broadcast=0, stale_reads=1),
            _metric("lazy", fetch=180, broadcast=0, stale_reads=2),
        ],
    }
    flattened = flatten_metrics(grouped)
    assert len(flattened) == 3

    aggregated = aggregate_comparison_runs(grouped)
    assert [a.strategy for a in aggregated] == ["eager", "lazy"]
    assert aggregated[0].broadcast_tokens_mean == 200.0
    assert aggregated[1].fetch_tokens_mean == 150.0
