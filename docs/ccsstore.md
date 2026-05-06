# CCSStore User Guide

Drop-in replacement for LangGraph's `InMemoryStore` that adds MESI cache
coherence — shared artifacts are fetched once per agent and invalidated
precisely when they change, instead of being rebroadcast on every step.

---

## Contents

1. [Installation](#installation)
2. [Quick start](#quick-start)
3. [Namespace convention](#namespace-convention)
4. [Strategies](#strategies)
5. [Observability](#observability)
6. [State transitions log](#state-transitions-log)
7. [Inline benchmark mode](#inline-benchmark-mode)
8. [Telemetry](#telemetry)
9. [Graceful degradation](#graceful-degradation)
10. [Examples](#examples)
11. [Real-workload benchmarks](#real-workload-benchmarks)
12. [Benchmarking your own workload](#benchmarking-your-own-workload)
13. [API reference](#api-reference)

---

## Installation

```bash
# Core — LangGraph adapter only
pip install "agent-coherence[langgraph]"

# With OpenTelemetry metrics
pip install "agent-coherence[langgraph,otel]"

# With LangSmith tracing
pip install "agent-coherence[langgraph,langsmith]"

# Everything
pip install "agent-coherence[all]"
```

---

## Quick start

```python
# Before
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()

# After — one import change, no node code changes
from ccs.adapters import CCSStore
store = CCSStore(strategy="lazy")

graph = builder.compile(store=store)
```

Node code stays identical — `store.get()`, `store.put()`, and `store.search()` all
work the same way.

---

## Namespace convention

CCSStore overloads the `namespace` tuple that LangGraph passes to `get` and `put`:

| Position | Meaning | Example |
|----------|---------|---------|
| `namespace[0]` | Agent identity | `"planner"`, `"reviewer"` |
| `namespace[1:]` | Artifact scope | `("shared",)`, `("project", "v2")` |

**Two agents share an artifact when their scopes match:**

```python
# Both address the same "codebase" artifact
store.put(("reviewer_a", "shared"), "codebase", {...})
store.get(("reviewer_b", "shared"), "codebase")  # reads what reviewer_a wrote
```

**Agent-private artifacts:** include the agent name in the scope.

```python
store.put(("planner", "planner", "scratch"), "draft", {...})
# scope is ("planner", "scratch") — other agents cannot see this key
```

This convention is required. Namespaces with fewer than two elements raise
`ValueError`.

---

## Strategies

Pass `strategy=` to `CCSStore(...)` to control when invalidated entries are
re-fetched.

| Strategy | Behaviour | Best for |
|----------|-----------|----------|
| `"lazy"` *(default)* | Fetch on next read after invalidation | Most workloads |
| `"eager"` | Pre-fetch as soon as an invalidation signal arrives | Low-latency reads |
| `"lease"` | Entries expire after a TTL regardless of writes | Time-sensitive data |
| `"access_count"` | Fetch on every N-th access | High-read, low-write |
| `"broadcast"` | Always fetch — no local caching | Debugging, correctness testing |

Strategy-specific kwargs are forwarded directly:

```python
store = CCSStore(strategy="lease", lease_ticks=10)
store = CCSStore(strategy="access_count", threshold=3)
```

---

## Observability

Pass `on_metric` to receive a `StoreMetricEvent` after every operation:

```python
from ccs.adapters import CCSStore, StoreMetricEvent

events: list[StoreMetricEvent] = []
store = CCSStore(strategy="lazy", on_metric=events.append)

# ... run your graph ...

hits   = [e for e in events if e.operation == "get" and e.cache_hit]
misses = [e for e in events if e.operation == "get" and not e.cache_hit]
saved  = sum(e.tokens_consumed for e in misses) - len(hits)  # rough savings
```

### `StoreMetricEvent` fields

| Field | Type | Description |
|-------|------|-------------|
| `operation` | `str` | `"get"`, `"put"`, `"search.hit"`, or `"degraded"` |
| `namespace` | `tuple[str, ...]` | Full namespace including agent name |
| `key` | `str` | Artifact key |
| `agent_name` | `str` | First element of `namespace` |
| `tokens_consumed` | `int` | `1` on cache hit; estimated content size on miss |
| `cache_hit` | `bool` | `True` when served from local cache |
| `tick` | `int` | Logical clock at the time of the operation |

Token estimation: `max(1, len(json.dumps(value)) // 4)`. Override by including
`"__ccs_size_tokens__": N` in your artifact value.

---

## State transitions log

Pass `state_log` to receive a structured dict for every stable MESI state transition.
Intended for external tools — debuggers, visualizers, audit pipelines — that need to
correlate agent behavior with coherence state changes without coupling to CCS internals.

```python
import json

log = []
store = CCSStore(strategy="lazy", state_log=log.append)

# ... run your graph ...

# Write JSONL
with open("transitions.jsonl", "w") as f:
    for entry in log:
        f.write(json.dumps(entry) + "\n")
```

### Log entry schema

Each entry is a flat `dict` with exactly these eight keys:

| Field | Type | Description |
|-------|------|-------------|
| `tick` | `int` | Monotonic operation counter within this `CCSStore` session |
| `artifact_id` | `str` | UUID of the artifact whose per-agent state changed |
| `agent_id` | `str` | UUID of the agent whose state changed |
| `agent_name` | `str \| None` | Agent display name (resolved from `namespace[0]`); `None` for low-level registry callers |
| `from_state` | `str` | Previous state: `"MODIFIED"`, `"EXCLUSIVE"`, `"SHARED"`, or `"INVALID"` |
| `to_state` | `str` | New state after the transition |
| `trigger` | `str` | Coordinator operation that caused the transition (see table below) |
| `version` | `int` | Artifact version number at the moment of the transition |

### Trigger vocabulary

| `trigger` | Fires when |
|-----------|-----------|
| `"register"` | Initial artifact registration; registering agent receives EXCLUSIVE |
| `"fetch"` | Fetch grant; agent transitions to SHARED or EXCLUSIVE |
| `"write"` | Write request; peers are invalidated (→ INVALID), requester receives EXCLUSIVE |
| `"commit"` | Write commit; peers are invalidated (→ INVALID), committer transitions to MODIFIED |
| `"invalidate"` | Explicit invalidation signal; agent transitions to INVALID |
| `"timeout"` | Transient state timeout; agent force-invalidated (→ INVALID) |

### Error handling

The callback is called synchronously on the critical path. An exception in `state_log`
propagates out of the coordinator operation and may leave the log incomplete for that
batch. Provide a callback that catches its own exceptions for production use:

```python
def safe_log(entry: dict) -> None:
    try:
        emit_to_pipeline(entry)
    except Exception:
        logger.exception("state_log callback failed")

store = CCSStore(strategy="lazy", state_log=safe_log)
```

`state_log=None` (default) adds no overhead — the guard is a single `is not None` check.

---

## Inline benchmark mode

Measure token savings on your own workload without any external tooling:

```python
store = CCSStore(strategy="lazy", benchmark=True)

# ... run your graph ...

store.print_benchmark_summary()
```

`benchmark=False` (default) adds zero overhead — no counters are allocated.

For programmatic access, use `benchmark_summary()`:

```python
summary = store.benchmark_summary()
# {
#   "baseline_tokens": 4160,
#   "ccs_tokens": 1301,
#   "tokens_saved": 2859,
#   "token_reduction_pct": 68.7,
#   "cache_hit_rate": 0.75,
#   "n_operations": 16,
# }
```

`benchmark_summary()` raises `RuntimeError` if the store was not created with
`benchmark=True`.

---

## Telemetry

Structured metrics without changing node code.

### OpenTelemetry

```bash
pip install "agent-coherence[otel]"
```

```python
store = CCSStore(strategy="lazy", telemetry="opentelemetry")
```

CCSStore creates two Counter instruments on the globally-configured
`MeterProvider`:

| Instrument | Unit | Attributes |
|------------|------|------------|
| `ccs.store.operations` | `{operation}` | `ccs.operation`, `ccs.agent_name`, `ccs.cache_hit` |
| `ccs.store.tokens_consumed` | `{token}` | `ccs.operation`, `ccs.agent_name`, `ccs.cache_hit` |

If no SDK is configured, the OTel no-op provider discards everything at zero cost.

To use a specific provider instead of the global one:

```python
from ccs.adapters.telemetry.otel import OtelExporter
store = CCSStore(strategy="lazy", telemetry=OtelExporter(meter_provider=my_provider))
```

### LangSmith

```bash
pip install "agent-coherence[langsmith]"
```

```python
store = CCSStore(strategy="lazy", telemetry="langsmith")
```

Per-operation metadata is attached to the active LangSmith run tree via
`run.add_metadata(...)`. Keys attached to each event:

```
ccs.operation, ccs.agent_name, ccs.tokens_consumed, ccs.cache_hit, ccs.tick
```

If no LangSmith run is active, events are silently discarded.

### Custom exporter

```python
from ccs.adapters import TelemetryExporter, StoreMetricEvent

class DatadogExporter(TelemetryExporter):
    def on_event(self, event: StoreMetricEvent) -> None:
        statsd.increment("ccs.operations", tags=[f"agent:{event.agent_name}"])
        statsd.histogram("ccs.tokens", event.tokens_consumed)

store = CCSStore(strategy="lazy", telemetry=DatadogExporter())
```

`on_metric` and `telemetry` are independent — both fire for every event if both
are set.

---

## Graceful degradation

By default (`on_error="strict"`), a `CoherenceError` propagates and the graph
fails. Use `on_error="degrade"` to keep the graph running when the coherence
layer encounters an unexpected state:

```python
store = CCSStore(strategy="lazy", on_error="degrade")
```

In degrade mode:

- **`put`**: if `core.write` raises, the value is stored in a plain dict fallback
  and a `"degraded"` operation event is emitted.
- **`get`**: if `core.read` raises, the value is retrieved from the fallback dict
  (empty dict if nothing was previously stored there) and a `"degraded"` event
  is emitted.

A warning is logged at `WARNING` level for each degraded operation. Monitor
degradations via `on_metric`:

```python
events = []
store = CCSStore(strategy="lazy", on_error="degrade", on_metric=events.append)

# ... run graph ...

degraded = [e for e in events if e.operation == "degraded"]
if degraded:
    alert(f"{len(degraded)} degraded operations detected")
```

Use `on_error="strict"` (the default) in development and CI. Consider
`on_error="degrade"` in production environments where a coherence bug should not
take down the whole graph.

Two attributes let you check degradation state after the fact:

```python
store.is_degraded       # True after the first degraded operation
store.degradation_count  # total number of degraded operations
```

Use these to gate alerts or health checks without keeping a separate event list.

---

## Examples

All examples are runnable with `python -m examples.<name>.main` from the project root.

| Example | Command | What it shows |
|---------|---------|---------------|
| LangGraph planner | `python -m examples.langgraph_planner.main` | 4-agent, 1 artifact, 75% hit rate |
| Code review pipeline | `python -m examples.code_review.main` | 3-agent, SHARED state transitions |
| Research pipeline | `python -m examples.research_pipeline.main` | 4-agent, 3 artifacts, 60% hit rate |
| Shared codebase | `python -m examples.shared_codebase.main` | 4-agent code review, 37.6% savings, benchmark output |

### Code review pipeline

Three agents share a codebase artifact. The key behavior: `reviewer_b` reads the
same codebase that `reviewer_a` cached without either agent invalidating it, because
neither wrote to it. Both hold it in SHARED state simultaneously.

### Research pipeline

Four agents operate on three artifacts (`brief`, `findings`, `analysis`). The key
behavior: `researcher`'s write to `findings` does **not** invalidate `brief` held
by `analyst` — each artifact key has its own independent MESI state per agent.

---

## Real-workload benchmarks

Results from real LangGraph graph executions using `GenericFakeChatModel` (no live
LLM calls). Run them yourself:

```bash
pip install "agent-coherence[langgraph,benchmark]"
make benchmark    # all three workloads, prints consolidated table
```

Or run individually:

```bash
python benchmarks/langgraph_real/bench_planner.py
python benchmarks/langgraph_real/bench_code_review.py
python benchmarks/langgraph_real/bench_high_churn.py
```

| Workload | Agents | Hit rate | Baseline | CCSStore | Savings |
|----------|--------|----------|----------|----------|---------|
| Planning (read-heavy) | 4 | 75% | 4,160 | 1,301 | 69% |
| Code review (write-moderate) | 3 | 60% | 5,320 | 2,835 | 47% |
| High-churn (write-heavy) | 4 | 50% | 3,250 | 2,317 | 29% |

*Tokens are approximate; real LLM content will vary.*

Hit rate and savings are lower-bounded by write frequency: more writes mean more
invalidations, more misses. The planning workload has 1 write and 12 reads (75% hit
rate). The high-churn workload has 4 writes and 8 reads (50% hit rate).

For the simulation-based results from the paper (84–95% savings), see
[REPRODUCE.md](../REPRODUCE.md).

---

## Benchmarking your own workload

```bash
pip install "agent-coherence[langgraph,benchmark]"
ccs-benchmark --graph path/to/my_graph.py:build_graph
```

The factory function must accept a single `store` argument and return a compiled
LangGraph graph:

```python
def build_graph(store):
    builder = StateGraph(...)
    # ... add nodes/edges ...
    return builder.compile(store=store)
```

Pass a custom input state with `--initial-state`:

```bash
ccs-benchmark --graph my_graph.py:build_graph --initial-state '{"query": "hello"}'
```

The CLI runs the graph once and prints `print_benchmark_summary()` output. For
inline benchmarking without the CLI, see [Inline benchmark mode](#inline-benchmark-mode).

---

## API reference

### `CCSStore(strategy, benchmark, on_metric, telemetry, on_error, state_log, **strategy_kwargs)`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `strategy` | `str` | `"lazy"` | Synchronization strategy: `"lazy"`, `"eager"`, `"lease"`, `"access_count"`, `"broadcast"` |
| `benchmark` | `bool` | `False` | Enable inline token-savings measurement; access results via `benchmark_summary()` / `print_benchmark_summary()` |
| `on_metric` | `Callable[[StoreMetricEvent], None] \| None` | `None` | Callback fired after every operation with per-op metrics |
| `telemetry` | `str \| TelemetryExporter \| None` | `None` | `"opentelemetry"`, `"langsmith"`, a `TelemetryExporter` instance, or `None` |
| `on_error` | `str` | `"strict"` | `"strict"` to propagate `CoherenceError`; `"degrade"` to fall back silently |
| `state_log` | `Callable[[dict], None] \| None` | `None` | Callback fired on every stable MESI state transition; see [State transitions log](#state-transitions-log) |
| `**strategy_kwargs` | `Any` | — | Forwarded to the strategy constructor (`lease_ticks`, `threshold`, etc.) |

### Public imports

```python
from ccs.adapters import (
    CCSStore,
    StoreMetricEvent,
    TelemetryExporter,
    NoOpTelemetryExporter,
    OtelExporter,
    LangSmithExporter,
    build_telemetry,
)
```
