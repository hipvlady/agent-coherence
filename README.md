# agent-coherence

**Cache coherence for multi-agent LLM systems.** Cut synchronization
tokens by 84-95% by fetching shared artifacts on demand and invalidating
peers when they change instead of rebroadcasting full context every
step.

Drop-in adapters for LangGraph, CrewAI, and AutoGen.
TLA+-verified safety properties. Apache 2.0.

[![CI](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml/badge.svg)](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-coherence)](https://pypi.org/project/agent-coherence/)
[![arXiv](https://img.shields.io/badge/arXiv-2603.15183-b31b1b)](https://arxiv.org/abs/2603.15183)

---

## The problem

When multiple agents share working context - a plan, a codebase, a
research document - most orchestration frameworks broadcast the full
artifact to every agent on every step. On workloads with four or more
agents and non-trivial artifacts, synchronization tokens dominate total
cost.

This is the same problem multi-core CPUs solved in the 1980s with MESI
cache coherence. `agent-coherence` applies that protocol to shared
artifacts in multi-agent pipelines.

## Install

```bash
pip install agent-coherence
```

## Quick start - LangGraph

```python
from ccs.adapters.langgraph import LangGraphAdapter

adapter = LangGraphAdapter(strategy_name="lazy")

# Register agents and shared artifacts
for name in ("planner", "researcher", "executor"):
    adapter.register_agent(name)

plan = adapter.register_artifact(name="plan.md", content="v1")

# Before a node runs - fetch only if the local cache is invalid
context = adapter.before_node(
    agent_name="planner",
    artifact_ids=[plan.id],
    now_tick=1,
)

# After a node writes - peers are invalidated, not re-broadcast
adapter.commit_outputs(
    agent_name="planner",
    writes={plan.id: context[plan.id]["content"] + "\nStep 1: gather reqs"},
    now_tick=2,
)
```

The next time `researcher` or `executor` reads `plan.md`, it fetches
once and re-caches. Other artifacts they hold stay warm. Adapters for
CrewAI and AutoGen use the same `before_node` / `commit_outputs`
surface.

Full example in
[`examples/multi_agent_planning.py`](examples/multi_agent_planning.py).

## CCSStore — LangGraph BaseStore with coherence

Replace `InMemoryStore` in an existing LangGraph graph with one import change:

```bash
pip install "agent-coherence[langgraph]"
```

```python
# Before
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()

# After — no other changes to node code required
from ccs.adapters import CCSStore
store = CCSStore(strategy="lazy")

graph = builder.compile(store=store)
```

**Namespace convention:** `namespace[0]` is the agent identity; `namespace[1:]` is
the artifact scope. Two agents writing to `("planner", "shared")` and
`("reviewer", "shared")` address the same artifact — shared state is the common
case. For agent-private artifacts, include the agent name in the scope:
`("planner", "planner", "private")`.

**Observability** — pass `on_metric` to measure token savings:

```python
from ccs.adapters import CCSStore, StoreMetricEvent

events = []
store = CCSStore(strategy="lazy", on_metric=events.append)
```

Each `StoreMetricEvent` carries `operation`, `cache_hit`, `tokens_consumed`, and
`tick`. See [`examples/langgraph_planner/`](examples/langgraph_planner/) for a
4-agent demo showing ~67% token reduction at a 4:1 read/write ratio.

**v0 scope:** in-memory only. Users swapping from `PostgresStore` take a durability
regression — persistent backends are v0.2 scope.

### Reproducing the paper's 95% number

The 95% figure in the benchmarks table comes from the simulation suite, not the
LangGraph example. To reproduce it:

```bash
make reproduce
```

This runs the simulation suite in `benchmarks/` over the paper's Planning workload
(large `n`, high read/write ratio, many epochs, simulated over hundreds of ticks).
The `examples/langgraph_planner/` demo shows CCSStore saving real tokens on a
realistic graph — these are two separate claims and two separate entry points.

## Benchmarks

Four canonical multi-agent workloads, `n=4` agents, `m=3` artifacts at
4,096 tokens each, 40 steps, 10 runs per config:

| Workload    | Broadcast (baseline) | Coherent       | Savings |
|-------------|----------------------|----------------|---------|
| Planning    | 1,979,597 tokens     | 99,081         | 95.0%   |
| Analysis    | 1,979,597 tokens     | 152,729        | 92.3%   |
| Development | 1,979,597 tokens     | 232,021        | 88.3%   |
| High-Churn  | 1,979,597 tokens     | 313,012        | 84.2%   |

Reproduce with `bash reproduce.sh`. See
[REPRODUCE.md](REPRODUCE.md) for output mapping and baseline verification.
Full protocol specification and experimental setup in
[the paper](https://arxiv.org/abs/2603.15183).

## How it works

Each shared artifact sits in one of four MESI states per agent:
**Modified**, **Exclusive**, **Shared**, or **Invalid**. A coordinator
tracks directory state and publishes invalidation signals when any
agent writes.

- **Reads** fetch only when the local cache is Invalid. Otherwise they
  hit the local cache at zero token cost.
- **Writes** are committed to the coordinator, which publishes
  lightweight invalidation signals (12 tokens) to peers instead of
  rebroadcasting the artifact itself.
- **Consistency** is single-writer-multiple-reader per artifact, with
  bounded staleness - peers re-fetch on next read.

Four synchronization strategies ship out of the box: `lazy` (default),
`eager`, `lease` (TTL-based), and `access_count`.

## Architecture

`agent-coherence` is structured as four composable layers:

- **Protocol** (`ccs.core`, `ccs.strategies`) - MESI state machine and
  synchronization strategies. No framework dependencies.
- **Coordinator** (`ccs.coordinator`) - Authority service tracking
  directory state and publishing invalidations. Runs in-process or
  out-of-process.
- **Event bus** (`ccs.bus`) - Pluggable transport for invalidation
  signals. Ships with an in-memory bus; production deployments can swap
  in Redis, Kafka, NATS, or gRPC streams.
- **Adapters** (`ccs.adapters`) - Framework integrations for LangGraph,
  CrewAI, and AutoGen. Each ~100 lines; adding a new framework is
  straightforward.

Each layer is independently useful and independently replaceable.

## Guarantees

The protocol is specified in TLA+ and model-checked with TLC. Verified
properties:

- **Safety** - Single-writer-multiple-reader per artifact and monotonic
  versions
- **Token Coherence Theorem** - Lower bound on savings vs. broadcast for
  any workload with write probability < 1
- **Liveness** - Every invalidated cache eventually reaches a valid
  state

See Section 6 of [the paper](https://arxiv.org/abs/2603.15183) for the
formal model and proof details.

## Why not just...

**...use mem0 or Letta?** Retrieval-based memory does not solve
concurrency. Two agents retrieving the same artifact and writing
independently will clobber each other. `agent-coherence` is a coherence
*protocol*, not a memory store - it composes with any retrieval
backend.

**...use LangGraph's `BaseStore`?** `BaseStore` provides persistence, not
concurrency safety. The LangGraph docs explicitly warn users to handle
concurrent writes themselves. `agent-coherence` is the layer that does
that.

**...use A2A?** A2A is the transport layer - how agents send tasks to
each other. `agent-coherence` is the artifact coherence layer - how
agents share state *while* they work. They compose.

**...use Anthropic / OpenAI prompt caching?** Provider-side caching
reduces per-agent prompt overhead but does not address inter-agent
artifact synchronization. The two are complementary: prompt caching
keeps the prefix cheap; coherence keeps the shared artifacts lean.

## Status

`v0.1` ships the protocol, simulation-based benchmarks, and adapters
for three frameworks. The library is designed to run standalone - the
coordinator, adapters, and strategies are all Apache 2.0 and
production-deployable on your own infrastructure.

Coming in `v0.2`:

- Production benchmarks on real LangGraph deployments
- Telemetry exporters (OpenTelemetry, LangSmith)
- Optimistic-locking strategy for high-contention workloads
- Async coordinator for large agent fleets

This is an alpha release. APIs may change before `v1.0`.

## Paper

**Token Coherence: Adapting MESI Cache Protocols to Minimize
Synchronization Overhead in Multi-Agent LLM Systems**
arXiv:[2603.15183](https://arxiv.org/abs/2603.15183)

<details>
<summary>BibTeX</summary>

```bibtex
@article{parakhin2026token,
  title   = {Token Coherence: Adapting MESI Cache Protocols to Minimize
             Synchronization Overhead in Multi-Agent LLM Systems},
  author  = {Parakhin, Vladyslav},
  journal = {arXiv preprint arXiv:2603.15183},
  year    = {2026}
}
```

</details>

## License

Apache-2.0. See [LICENSE](LICENSE).
