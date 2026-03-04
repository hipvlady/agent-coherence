"""Deterministic simulation engine for coherence strategy evaluation."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Any, Mapping, Sequence
from uuid import UUID

from ccs.coordinator.registry import ArtifactRegistry
from ccs.coordinator.service import CoordinatorService
from ccs.core.clock import LogicalClock
from ccs.core.states import MESIState
from ccs.core.types import Artifact, ArtifactCacheEntry, FetchRequest, InvalidationSignal
from ccs.strategies.base import SyncStrategy
from ccs.strategies.selector import build_strategy
from ccs.transport.network_sim import NetworkMessage, NetworkSimulator

from .aggregation import aggregate_comparison_runs, flatten_metrics
from .consistency import ConsistencyMonitor
from .metrics import SimulationMetrics, StrategyComparisonReport

_INVALIDATION_SIGNAL_TOKENS = 12


class SimulationEngine:
    """Runs one scenario/strategy pair and returns a metrics payload."""

    def __init__(
        self,
        scenario_config: Mapping[str, Any],
        *,
        strategy_name: str,
        seed: int | None = None,
    ) -> None:
        self._config = scenario_config
        simulation = scenario_config["simulation"]
        strategy_cfg = scenario_config.get("strategies", {})
        lease_cfg = strategy_cfg.get("lease", {})
        access_count_cfg = strategy_cfg.get("access_count", {})

        self.seed = int(simulation["seed"] if seed is None else seed)
        self._rng = random.Random(self.seed)
        self._clock = LogicalClock()
        self._registry = ArtifactRegistry()
        self._coordinator = CoordinatorService(self._registry)
        self._strategy: SyncStrategy = build_strategy(
            strategy_name,
            lease_ttl_ticks=int(lease_cfg.get("default_ttl_ticks", 300)),
            access_count_max_accesses=int(access_count_cfg.get("max_accesses", 100)),
        )
        self._monitor = ConsistencyMonitor(self._strategy)
        self._network = NetworkSimulator(
            latency_ticks=int(scenario_config["network"]["latency_ticks"]),
            message_loss_rate=float(scenario_config["network"]["message_loss_rate"]),
            rng=self._rng,
        )

        self._agent_ids = [UUID(int=i + 1) for i in range(int(simulation["num_agents"]))]
        self._cache_by_agent: dict[UUID, dict[UUID, ArtifactCacheEntry]] = {
            agent_id: {} for agent_id in self._agent_ids
        }
        self._artifact_ids: list[UUID] = []
        self._artifact_specs_by_id: dict[UUID, dict[str, Any]] = {}
        self._register_artifacts()

        # Counters collected into SimulationMetrics at end of run.
        self._total_actions = 0
        self._read_actions = 0
        self._write_actions = 0
        self._fetch_actions = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._invalidations_issued = 0
        self._invalidations_delivered = 0
        self._updates_issued = 0
        self._updates_delivered = 0
        self._tokens_fetch = 0
        self._tokens_broadcast = 0
        self._tokens_invalidation = 0
        self._context_injections = 0

    def run(self) -> SimulationMetrics:
        """Run one deterministic simulation and return collected metrics."""
        duration_ticks = int(self._config["simulation"]["duration_ticks"])
        for _ in range(duration_ticks):
            self._deliver_messages()
            self._execute_actions_for_tick()
            self._clock.advance()

        # Drain messages that become due exactly at final tick.
        self._deliver_messages()
        return self._build_metrics(duration_ticks)

    def _register_artifacts(self) -> None:
        for artifact_cfg in self._config["artifacts"]:
            artifact = Artifact(
                name=str(artifact_cfg["id"]),
                version=int(artifact_cfg.get("initial_version", 1)),
                size_tokens=int(artifact_cfg["size_tokens"]),
            )
            self._registry.register_artifact(
                artifact,
                content=f"{artifact.name}-v{artifact.version}",
            )
            self._artifact_ids.append(artifact.id)
            self._artifact_specs_by_id[artifact.id] = dict(artifact_cfg)

    def _execute_actions_for_tick(self) -> None:
        now = self._clock.now()
        scenario = self._config["scenario"]
        action_probability = scenario.get("action_probability")
        agent_velocity = scenario.get("agent_velocity")

        for agent_id in self._agent_ids:
            if agent_velocity is not None:
                for _ in range(int(agent_velocity)):
                    self._execute_single_action(agent_id=agent_id, now_tick=now)
                continue

            assert action_probability is not None
            if self._rng.random() < float(action_probability):
                self._execute_single_action(agent_id=agent_id, now_tick=now)

    def _execute_single_action(self, *, agent_id: UUID, now_tick: int) -> None:
        self._total_actions += 1
        artifact_id = self._choose_artifact_id()
        artifact_cfg = self._artifact_specs_by_id[artifact_id]
        write_probability = self._effective_write_probability()
        mutable = bool(artifact_cfg.get("mutable", True))
        is_write = mutable and self._rng.random() < write_probability

        if is_write:
            self._perform_write(agent_id=agent_id, artifact_id=artifact_id, now_tick=now_tick)
        else:
            self._perform_read(agent_id=agent_id, artifact_id=artifact_id, now_tick=now_tick)

    def _perform_read(self, *, agent_id: UUID, artifact_id: UUID, now_tick: int) -> None:
        self._read_actions += 1
        local_cache = self._cache_by_agent[agent_id]
        entry = local_cache.get(artifact_id)

        if entry is None:
            self._cache_misses += 1
            self._fetch(agent_id=agent_id, artifact_id=artifact_id, now_tick=now_tick)
            return

        if self._strategy.requires_refresh(entry, now_tick=now_tick):
            self._cache_misses += 1
            self._fetch(agent_id=agent_id, artifact_id=artifact_id, now_tick=now_tick)
            return

        canonical = self._registry.get_artifact(artifact_id)
        assert canonical is not None
        stale = entry.state != MESIState.INVALID and entry.local_version < canonical.version
        self._monitor.record_read(agent_id=agent_id, artifact_id=artifact_id, stale=stale)
        self._cache_hits += 1
        local_cache[artifact_id] = self._strategy.on_read(entry, now_tick=now_tick)

    def _perform_write(self, *, agent_id: UUID, artifact_id: UUID, now_tick: int) -> None:
        self._write_actions += 1
        local_cache = self._cache_by_agent[agent_id]
        entry = local_cache.get(artifact_id)
        if entry is None or self._strategy.requires_refresh(entry, now_tick=now_tick):
            self._cache_misses += 1
            self._fetch(agent_id=agent_id, artifact_id=artifact_id, now_tick=now_tick)

        peers_to_sync = [
            peer_id
            for peer_id, state in self._registry.get_state_map(artifact_id).items()
            if peer_id != agent_id and state != MESIState.INVALID
        ]
        previous = self._registry.get_artifact(artifact_id)
        assert previous is not None

        self._coordinator.write(agent_id=agent_id, artifact_id=artifact_id)
        updated, _ = self._coordinator.commit(
            agent_id=agent_id,
            artifact_id=artifact_id,
            content=f"{previous.name}-v{previous.version + 1}-t{now_tick}",
            size_tokens=previous.size_tokens,
        )
        self._monitor.validate_monotonic(previous.version, updated.version)

        local_cache[artifact_id] = self._strategy.on_fetch(
            artifact_id=artifact_id,
            version=updated.version,
            state=MESIState.MODIFIED,
            now_tick=now_tick,
        )
        self._monitor.reset_stale_steps(agent_id=agent_id, artifact_id=artifact_id)

        if self._strategy.broadcasts_content_on_commit():
            self._broadcast_update(
                writer_agent_id=agent_id,
                peers=peers_to_sync,
                artifact_id=artifact_id,
                version=updated.version,
                now_tick=now_tick,
            )
        elif self._strategy.invalidates_peers_on_commit():
            self._emit_invalidations(
                writer_agent_id=agent_id,
                peers=peers_to_sync,
                artifact_id=artifact_id,
                version=updated.version,
                now_tick=now_tick,
            )

        self._monitor.validate_single_writer(self._registry.get_state_map(artifact_id))

    def _fetch(self, *, agent_id: UUID, artifact_id: UUID, now_tick: int) -> None:
        response = self._coordinator.fetch(
            FetchRequest(
                artifact_id=artifact_id,
                requesting_agent_id=agent_id,
                requested_at_tick=now_tick,
            )
        )
        self._fetch_actions += 1
        self._context_injections += 1
        self._tokens_fetch += self._artifact_token_size(artifact_id)
        self._cache_by_agent[agent_id][artifact_id] = self._strategy.on_fetch(
            artifact_id=artifact_id,
            version=response.version,
            state=response.state_grant,
            now_tick=now_tick,
        )
        self._monitor.reset_stale_steps(agent_id=agent_id, artifact_id=artifact_id)
        self._monitor.validate_single_writer(self._registry.get_state_map(artifact_id))

    def _emit_invalidations(
        self,
        *,
        writer_agent_id: UUID,
        peers: Sequence[UUID],
        artifact_id: UUID,
        version: int,
        now_tick: int,
    ) -> None:
        for peer_id in peers:
            signal = InvalidationSignal(
                artifact_id=artifact_id,
                new_version=version,
                issued_at_tick=now_tick,
                issuer_agent_id=writer_agent_id,
            )
            self._network.send(
                payload=signal,
                source=writer_agent_id,
                destination=peer_id,
                current_tick=now_tick,
                message_type="invalidate",
            )
            self._invalidations_issued += 1
            self._tokens_invalidation += _INVALIDATION_SIGNAL_TOKENS

    def _broadcast_update(
        self,
        *,
        writer_agent_id: UUID,
        peers: Sequence[UUID],
        artifact_id: UUID,
        version: int,
        now_tick: int,
    ) -> None:
        for peer_id in peers:
            self._network.send(
                payload={
                    "artifact_id": artifact_id,
                    "version": version,
                    "writer_agent_id": writer_agent_id,
                },
                source=writer_agent_id,
                destination=peer_id,
                current_tick=now_tick,
                message_type="update",
            )
            self._updates_issued += 1
            self._tokens_broadcast += self._artifact_token_size(artifact_id)
            self._context_injections += 1

    def _deliver_messages(self) -> None:
        for message in self._network.deliver_due(self._clock.now()):
            self._deliver_message(message)

    def _deliver_message(self, message: NetworkMessage) -> None:
        if message.message_type == "invalidate":
            self._apply_invalidation(message)
            return
        if message.message_type == "update":
            self._apply_update(message)
            return
        raise ValueError(f"unsupported message type '{message.message_type}'")

    def _apply_invalidation(self, message: NetworkMessage) -> None:
        signal = message.payload
        assert isinstance(signal, InvalidationSignal)
        local_cache = self._cache_by_agent[message.destination]
        entry = local_cache.get(signal.artifact_id)
        if entry is None:
            local_cache[signal.artifact_id] = ArtifactCacheEntry(
                artifact_id=signal.artifact_id,
                state=MESIState.INVALID,
                local_version=max(signal.new_version - 1, 0),
                access_count=0,
                acquired_at_tick=signal.issued_at_tick,
            )
        else:
            local_cache[signal.artifact_id] = replace(entry, state=MESIState.INVALID)

        self._coordinator.invalidate(
            agent_id=message.destination,
            artifact_id=signal.artifact_id,
            new_version=signal.new_version,
            issuer_agent_id=signal.issuer_agent_id,
            issued_at_tick=signal.issued_at_tick,
        )
        self._monitor.reset_stale_steps(agent_id=message.destination, artifact_id=signal.artifact_id)
        self._invalidations_delivered += 1
        self._monitor.validate_single_writer(self._registry.get_state_map(signal.artifact_id))

    def _apply_update(self, message: NetworkMessage) -> None:
        payload = message.payload
        artifact_id = payload["artifact_id"]
        version = int(payload["version"])
        writer_agent_id = payload["writer_agent_id"]
        local_cache = self._cache_by_agent[message.destination]
        local_cache[artifact_id] = self._strategy.on_fetch(
            artifact_id=artifact_id,
            version=version,
            state=MESIState.SHARED,
            now_tick=self._clock.now(),
        )

        self._registry.set_agent_state(artifact_id, message.destination, MESIState.SHARED)
        self._registry.set_agent_state(artifact_id, writer_agent_id, MESIState.SHARED)
        self._monitor.reset_stale_steps(agent_id=message.destination, artifact_id=artifact_id)
        self._updates_delivered += 1
        self._monitor.validate_single_writer(self._registry.get_state_map(artifact_id))

    def _artifact_token_size(self, artifact_id: UUID) -> int:
        artifact = self._registry.get_artifact(artifact_id)
        assert artifact is not None
        return int(artifact.size_tokens or 1)

    def _choose_artifact_id(self) -> UUID:
        workload = self._config["scenario"]["workload"]
        if workload != "large_artifact_reasoning":
            return self._rng.choice(self._artifact_ids)

        weights = [float(self._artifact_token_size(artifact_id)) for artifact_id in self._artifact_ids]
        return self._rng.choices(self._artifact_ids, weights=weights, k=1)[0]

    def _effective_write_probability(self) -> float:
        base = float(self._config["scenario"]["write_probability"])
        workload = self._config["scenario"]["workload"]
        if workload == "read_heavy":
            return min(base, 0.2)
        if workload == "write_heavy":
            return max(base, 0.7)
        if workload == "parallel_editing":
            return max(base, 0.5)
        if workload == "large_artifact_reasoning":
            return min(base, 0.3)
        return base

    def _build_metrics(self, duration_ticks: int) -> SimulationMetrics:
        return SimulationMetrics(
            scenario=str(self._config["scenario"]["name"]),
            strategy=self._strategy.name,
            seed=self.seed,
            duration_ticks=duration_ticks,
            agent_count=len(self._agent_ids),
            artifact_count=len(self._artifact_ids),
            total_actions=self._total_actions,
            read_actions=self._read_actions,
            write_actions=self._write_actions,
            fetch_actions=self._fetch_actions,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            stale_reads=self._monitor.stale_reads,
            max_stale_steps=self._monitor.max_stale_steps,
            staleness_bound_violations=self._monitor.staleness_bound_violations,
            swmr_violations=self._monitor.swmr_violations,
            monotonic_version_violations=self._monitor.monotonic_version_violations,
            invalidations_issued=self._invalidations_issued,
            invalidations_delivered=self._invalidations_delivered,
            updates_issued=self._updates_issued,
            updates_delivered=self._updates_delivered,
            message_overhead=self._network.message_overhead,
            tokens_fetch=self._tokens_fetch,
            tokens_broadcast=self._tokens_broadcast,
            tokens_invalidation=self._tokens_invalidation,
            context_injections=self._context_injections,
        )


def run_strategy_range(
    scenario_config: Mapping[str, Any],
    *,
    strategy_name: str,
    runs: int,
    seed_start: int,
) -> list[SimulationMetrics]:
    """Run one strategy across a contiguous seed range."""
    if runs < 1:
        raise ValueError("runs must be >= 1")
    metrics: list[SimulationMetrics] = []
    for offset in range(runs):
        engine = SimulationEngine(
            scenario_config,
            strategy_name=strategy_name,
            seed=seed_start + offset,
        )
        metrics.append(engine.run())
    return metrics


def run_strategy_comparison(
    scenario_config: Mapping[str, Any],
    *,
    strategies: Sequence[str],
    runs: int,
    seed_start: int = 0,
) -> StrategyComparisonReport:
    """Run multi-strategy comparison and return report payload."""
    metrics_by_strategy: dict[str, list[SimulationMetrics]] = {}
    for strategy_name in strategies:
        metrics_by_strategy[strategy_name] = run_strategy_range(
            scenario_config,
            strategy_name=strategy_name,
            runs=runs,
            seed_start=seed_start,
        )

    aggregated = [item.to_dict() for item in aggregate_comparison_runs(metrics_by_strategy)]
    scenario_name = str(scenario_config["scenario"]["name"])
    return StrategyComparisonReport(
        scenario=scenario_name,
        runs_per_strategy=runs,
        seed_start=seed_start,
        strategies=list(strategies),
        runs=flatten_metrics(metrics_by_strategy),
        aggregated=aggregated,
    )
