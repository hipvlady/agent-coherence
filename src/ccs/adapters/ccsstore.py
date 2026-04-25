# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""CCSStore: LangGraph BaseStore adapter with MESI-style cache coherence."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    MatchCondition,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

from ccs.adapters.base import CoherenceAdapterCore
from ccs.core.states import MESIState
from ccs.core.types import Artifact


@dataclass
class StoreMetricEvent:
    """Emitted by CCSStore for each artifact operation when on_metric is set."""

    operation: str
    namespace: tuple[str, ...]
    key: str
    agent_name: str
    tokens_consumed: int
    cache_hit: bool
    tick: int


class CCSStore(BaseStore):
    """Drop-in replacement for LangGraph's InMemoryStore with MESI cache coherence.

    A peer write invalidates all other agents' cached copies; their next get() is a
    cache miss (coordinator fetch) while subsequent reads within the same MESI grant
    are cache hits.

    Namespace convention: namespace[0] is the agent identity, namespace[1:] is the
    artifact scope. Two agents writing to ("planner", "shared") and ("reviewer",
    "shared") address the same artifact. For agent-private artifacts include the agent
    name in the scope: ("planner", "planner", "private").
    """

    def __init__(
        self,
        strategy: str = "lazy",
        on_metric: Callable[[StoreMetricEvent], None] | None = None,
        **strategy_kwargs: Any,
    ) -> None:
        self.core = CoherenceAdapterCore(strategy_name=strategy, **strategy_kwargs)
        self._on_metric = on_metric
        self._lock = threading.Lock()
        self._tick: int = 0
        # (scope, key) → artifact_id; scope is namespace[1:]
        self._artifact_map: dict[tuple[tuple[str, ...], str], uuid.UUID] = {}
        self._known_agents: set[str] = set()
        # artifact IDs removed via delete; bounded by distinct (scope, key) pairs ever deleted
        self._deleted_ids: set[uuid.UUID] = set()
        # full namespace (including agent) → set of keys; maintained on put/delete
        self._namespace_index: dict[tuple[str, ...], set[str]] = {}

    # ------------------------------------------------------------------
    # BaseStore interface — batch is the single implementation point
    # ------------------------------------------------------------------

    def batch(self, ops: Iterable[Any]) -> list[Result]:
        with self._lock:
            self._tick += 1
            tick = self._tick
            results: list[Any] = []
            for op in ops:
                if isinstance(op, GetOp):
                    results.append(self._apply_get(op, tick))
                elif isinstance(op, PutOp):
                    if op.value is None:
                        self._apply_delete(op.namespace, op.key, tick)
                    else:
                        self._apply_put(op, tick)
                    results.append(None)
                elif isinstance(op, SearchOp):
                    results.append(self._apply_search(op, tick))
                elif isinstance(op, ListNamespacesOp):
                    results.append(self._apply_list_namespaces(op))
                else:
                    results.append(None)
            return results

    async def abatch(self, ops: Iterable[Any]) -> list[Result]:
        return await asyncio.to_thread(self.batch, ops)

    # ------------------------------------------------------------------
    # Op handlers
    # ------------------------------------------------------------------

    def _apply_get(self, op: GetOp, tick: int) -> Item | None:
        namespace = op.namespace
        key = op.key
        if len(namespace) < 2:
            raise ValueError(
                f"CCSStore requires namespace with at least 2 elements; got {namespace!r}"
            )

        scope_key = (tuple(namespace[1:]), key)
        if scope_key not in self._artifact_map:
            return None

        artifact_id = self._artifact_map[scope_key]
        agent_name = namespace[0]
        self._ensure_agent_registered(agent_name)

        entry = self.core.runtime(agent_name).cache.get(artifact_id)
        cache_hit = entry is not None and entry.state in (
            MESIState.SHARED,
            MESIState.EXCLUSIVE,
            MESIState.MODIFIED,
        )

        if cache_hit:
            raw = self.core.runtime(agent_name).content(artifact_id)
            value = json.loads(raw) if raw else {}
        else:
            resp = self.core.read(agent_name=agent_name, artifact_id=artifact_id, now_tick=tick)
            value = json.loads(resp.content) if resp.content else {}

        if self._on_metric is not None:
            # Cache hit: no content was fetched from the coordinator, so transmission cost is 0.
            # We emit max(1, 0) = 1 to acknowledge the access without counting redundant transfer.
            tokens = 1 if cache_hit else self._estimate_tokens(value)
            self._on_metric(
                StoreMetricEvent(
                    operation="get",
                    namespace=namespace,
                    key=key,
                    agent_name=agent_name,
                    tokens_consumed=tokens,
                    cache_hit=cache_hit,
                    tick=tick,
                )
            )

        now = datetime.now(tz=timezone.utc)
        return Item(value=value, key=key, namespace=namespace, created_at=now, updated_at=now)

    def _apply_put(self, op: PutOp, tick: int) -> None:
        namespace = op.namespace
        key = op.key
        value = op.value
        if len(namespace) < 2:
            raise ValueError(
                f"CCSStore requires namespace with at least 2 elements; got {namespace!r}"
            )

        if op.ttl is not None:
            warnings.warn(
                "CCSStore does not enforce ttl in v0; the value will be stored without expiry.",
                UserWarning,
                stacklevel=2,
            )

        content_str = json.dumps(value, sort_keys=True, separators=(",", ":"))
        agent_name = namespace[0]

        self._ensure_agent_registered(agent_name)
        artifact_id = self._ensure_artifact_registered(namespace, key)

        self.core.write(
            agent_name=agent_name, artifact_id=artifact_id, content=content_str, now_tick=tick
        )

        full_ns = tuple(namespace)
        if full_ns not in self._namespace_index:
            self._namespace_index[full_ns] = set()
        self._namespace_index[full_ns].add(key)

        if self._on_metric is not None:
            self._on_metric(
                StoreMetricEvent(
                    operation="put",
                    namespace=namespace,
                    key=key,
                    agent_name=agent_name,
                    tokens_consumed=self._estimate_tokens(value),
                    cache_hit=False,
                    tick=tick,
                )
            )

    def _apply_delete(self, namespace: tuple[str, ...], key: str, tick: int) -> None:
        if len(namespace) < 2:
            raise ValueError(
                f"CCSStore requires namespace with at least 2 elements; got {namespace!r}"
            )

        scope_key = (tuple(namespace[1:]), key)
        if scope_key not in self._artifact_map:
            return

        agent_name = namespace[0]
        artifact_id = self._artifact_map[scope_key]

        self._ensure_agent_registered(agent_name)
        caller_agent_id = self.core.agent_id_for(agent_name)

        signals = self.core.coordinator.delete(
            agent_id=caller_agent_id,
            artifact_id=artifact_id,
            issued_at_tick=tick,
        )

        if signals:
            peers = [
                self.core.agent_id_for(n)
                for n in self.core.agent_names()
                if n != agent_name
            ]
            for signal in signals:
                self.core.event_bus.publish_invalidation(signal, recipients=peers)

        self._deleted_ids.add(artifact_id)
        self._artifact_map.pop(scope_key, None)

        full_ns = tuple(namespace)
        if full_ns in self._namespace_index:
            self._namespace_index[full_ns].discard(key)
            if not self._namespace_index[full_ns]:
                del self._namespace_index[full_ns]

    def _apply_search(self, op: SearchOp, tick: int) -> list[SearchItem]:
        # Caller holds self._lock — _apply_search is only reachable through batch/abatch.
        if op.query is not None:
            warnings.warn(
                "CCSStore does not support semantic search in v0; query= is ignored.",
                UserWarning,
                stacklevel=2,
            )

        prefix = op.namespace_prefix
        results: list[SearchItem] = []

        for full_ns, keys in list(self._namespace_index.items()):
            if not _ns_starts_with(full_ns, prefix):
                continue
            scope = tuple(full_ns[1:])
            for key in list(keys):
                artifact_id = self._artifact_map.get((scope, key))
                if artifact_id is None:
                    continue
                raw = self.core.registry.get_content(artifact_id)
                if raw is None:
                    continue
                value = json.loads(raw)

                if op.filter and not _matches_filter(value, op.filter):
                    continue

                now = datetime.now(tz=timezone.utc)
                results.append(
                    SearchItem(
                        namespace=full_ns,
                        key=key,
                        value=value,
                        created_at=now,
                        updated_at=now,
                    )
                )

                if self._on_metric is not None:
                    self._on_metric(
                        StoreMetricEvent(
                            operation="search.hit",
                            namespace=full_ns,
                            key=key,
                            agent_name=full_ns[0] if full_ns else "",
                            tokens_consumed=self._estimate_tokens(value),
                            cache_hit=False,
                            tick=tick,
                        )
                    )

        return results[op.offset : op.offset + op.limit]

    def _apply_list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        namespaces: list[tuple[str, ...]] = list(self._namespace_index.keys())

        conditions = op.match_conditions or ()
        if conditions:
            namespaces = [
                ns for ns in namespaces if all(_matches_condition(ns, c) for c in conditions)
            ]

        if op.max_depth is not None:
            namespaces = list({ns[: op.max_depth] for ns in namespaces})

        return namespaces[op.offset : op.offset + op.limit]

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def _ensure_agent_registered(self, agent_name: str) -> None:
        if agent_name not in self._known_agents:
            self.core.register_agent(agent_name)
            self._known_agents.add(agent_name)

    def _ensure_artifact_registered(self, namespace: tuple[str, ...], key: str) -> uuid.UUID:
        scope = tuple(namespace[1:])
        scope_str = ":".join(scope)
        artifact_id = uuid.uuid5(uuid.NAMESPACE_URL, f"ccs-artifact:{scope_str}:{key}")
        scope_key = (scope, key)

        if scope_key in self._artifact_map:
            return artifact_id

        if artifact_id in self._deleted_ids:
            self._deleted_ids.discard(artifact_id)

        self.core.registry.register_artifact(
            Artifact(id=artifact_id, name=f"{scope_str}:{key}", version=1),
            "",
        )
        self._artifact_map[scope_key] = artifact_id
        return artifact_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(value: dict[str, Any]) -> int:
        if "__ccs_size_tokens__" in value:
            return int(value["__ccs_size_tokens__"])
        return max(1, len(json.dumps(value, sort_keys=True, separators=(",", ":"))) // 4)


def _ns_starts_with(ns: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return ns[: len(prefix)] == prefix


def _matches_filter(value: dict[str, Any], filter_dict: dict[str, Any]) -> bool:
    for field, condition in filter_dict.items():
        if isinstance(condition, dict):
            for op_key, expected in condition.items():
                actual = value.get(field)
                if op_key == "$eq":
                    if actual != expected:
                        return False
                elif op_key == "$ne":
                    if actual == expected:
                        return False
                else:
                    raise NotImplementedError(
                        f"CCSStore search filter operator {op_key!r} is not supported in v0. "
                        "Only $eq and $ne are supported."
                    )
        else:
            if value.get(field) != condition:
                return False
    return True


def _matches_condition(ns: tuple[str, ...], cond: MatchCondition) -> bool:
    path = cond.path
    if "*" in path:
        raise NotImplementedError(
            "CCSStore does not support wildcard '*' in MatchCondition.path in v0."
        )
    if cond.match_type == "prefix":
        return ns[: len(path)] == path
    if cond.match_type == "suffix":
        return ns[len(ns) - len(path) :] == path
    return False
