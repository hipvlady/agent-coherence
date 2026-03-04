"""Integration tests for simulation engine and comparison runner."""

from __future__ import annotations

from ccs.simulation.engine import SimulationEngine, run_strategy_comparison, run_strategy_range


def _scenario() -> dict:
    return {
        "simulation": {
            "duration_ticks": 20,
            "num_agents": 4,
            "seed": 11,
            "action_probability": 0.6,
            "actions_per_tick": 1,
        },
        "network": {
            "latency_ticks": 0,
            "message_loss_rate": 0.0,
        },
        "scenario": {
            "name": "engine-smoke",
            "workload": "read_heavy",
            "action_probability": 0.6,
            "write_probability": 0.15,
            "agent_velocity": None,
            "revocation_tick": None,
        },
        "artifacts": [
            {"id": "plan.md", "size_tokens": 400, "volatility": 0.2, "initial_version": 1, "mutable": True},
            {"id": "facts.json", "size_tokens": 800, "volatility": 0.1, "initial_version": 1, "mutable": True},
        ],
        "strategies": {
            "eager": {},
            "lazy": {"check_interval_ticks": 2},
            "lease": {"default_ttl_ticks": 5},
            "access_count": {"max_accesses": 4},
            "exec_count": {"max_operations": 4},
        },
        "transient": {"timeout_ticks": 5},
        "context_semantics": {"model": "pointer"},
    }


def _scenario_with_model(model: str) -> dict:
    scenario = _scenario()
    scenario["context_semantics"]["model"] = model
    return scenario


def test_engine_run_returns_coherence_metrics() -> None:
    metrics = SimulationEngine(_scenario(), strategy_name="lazy", seed=5).run()

    assert metrics.strategy == "lazy"
    assert metrics.duration_ticks == 20
    assert metrics.agent_count == 4
    assert metrics.artifact_count == 2
    assert metrics.total_actions == metrics.read_actions + metrics.write_actions
    assert metrics.synchronization_tokens == (
        metrics.tokens_fetch + metrics.tokens_broadcast + metrics.tokens_invalidation
    )
    assert "crr" in metrics.to_dict()


def test_run_strategy_range_uses_seed_window() -> None:
    runs = run_strategy_range(_scenario(), strategy_name="access_count", runs=3, seed_start=100)
    assert len(runs) == 3
    assert [m.seed for m in runs] == [100, 101, 102]


def test_lazy_avoids_broadcast_tokens_compared_to_eager() -> None:
    lazy = SimulationEngine(_scenario(), strategy_name="lazy", seed=9).run()
    eager = SimulationEngine(_scenario(), strategy_name="eager", seed=9).run()

    assert lazy.tokens_broadcast == 0
    assert eager.tokens_broadcast >= 0
    assert eager.message_overhead >= lazy.message_overhead


def test_strategy_comparison_returns_dashboard_contract() -> None:
    report = run_strategy_comparison(
        _scenario(),
        strategies=["eager", "lazy"],
        runs=2,
        seed_start=40,
    )
    payload = report.to_dict()

    assert payload["scenario"] == "engine-smoke"
    assert payload["runs_per_strategy"] == 2
    assert payload["strategies"] == ["eager", "lazy"]
    assert len(payload["runs"]) == 4
    assert len(payload["aggregated"]) == 2


def test_same_seed_is_deterministic_for_engine_outputs() -> None:
    first = SimulationEngine(_scenario(), strategy_name="lazy", seed=123).run().to_dict()
    second = SimulationEngine(_scenario(), strategy_name="lazy", seed=123).run().to_dict()

    assert first == second


def test_engine_uses_agent_runtime_map_instead_of_legacy_cache_map() -> None:
    engine = SimulationEngine(_scenario(), strategy_name="lazy", seed=5)

    assert hasattr(engine, "_runtime_by_agent")
    assert not hasattr(engine, "_cache_by_agent")


def test_engine_reports_transient_timeouts_when_messages_are_delayed() -> None:
    scenario = _scenario()
    scenario["network"]["latency_ticks"] = 8
    scenario["simulation"]["duration_ticks"] = 12
    scenario["scenario"]["write_probability"] = 1.0
    scenario["scenario"]["action_probability"] = 1.0
    scenario["transient"]["timeout_ticks"] = 1

    metrics = SimulationEngine(scenario, strategy_name="lazy", seed=17).run()
    assert metrics.transient_state_timeouts >= 1


def test_always_read_forces_more_fetches_than_conditional() -> None:
    always = SimulationEngine(_scenario_with_model("always_read"), strategy_name="lazy", seed=22).run()
    conditional = SimulationEngine(_scenario_with_model("conditional_injection"), strategy_name="lazy", seed=22).run()

    assert always.fetch_actions >= conditional.fetch_actions
    assert always.tokens_fetch >= conditional.tokens_fetch


def test_pointer_model_reduces_eager_broadcast_token_cost() -> None:
    pointer = SimulationEngine(_scenario_with_model("pointer"), strategy_name="eager", seed=31).run()
    conditional = SimulationEngine(_scenario_with_model("conditional_injection"), strategy_name="eager", seed=31).run()

    assert pointer.tokens_broadcast <= conditional.tokens_broadcast
