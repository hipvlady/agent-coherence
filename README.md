# agent-coherence

**Drop-in replacement for LangGraph's `InMemoryStore` that cuts shared-state token
overhead by 47–69% on realistic multi-agent workloads.**

`agent-coherence` adapts the MESI cache coherence protocol, used in CPU caches
since 1984, to artifact synchronization across LLM agents. Instead of
rebroadcasting shared context to every agent on every step, agents hold valid
copies until something changes, then receive targeted invalidation.

[![CI](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml/badge.svg)](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-coherence)](https://pypi.org/project/agent-coherence/)
[![arXiv](https://img.shields.io/badge/arXiv-2603.15183-b31b1b)](https://arxiv.org/abs/2603.15183)

```python
# Before
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()

# After — one import change, no other code changes
from ccs.adapters import CCSStore
store = CCSStore(strategy="lazy")
```

- 📦 `pip install "agent-coherence[langgraph]"`
- 📄 [Paper on arXiv (2603.15183)](https://arxiv.org/abs/2603.15183) — formal protocol, TLA+ verification, simulation results
- 📊 [Real benchmarks](#real-workload-benchmarks) — measured on actual LangGraph graphs
- 🔧 [User guide](docs/ccsstore.md) — strategies, telemetry, examples

---

## The problem

When multiple agents share working context, a plan, a codebase, a research
document, most orchestration frameworks broadcast the full artifact to every
agent on every step. On workloads with four or more agents and non-trivial
artifacts, synchronization tokens dominate total cost.

This is the same problem multi-core CPUs solved with MESI cache coherence.
`agent-coherence` applies that protocol to shared artifacts in multi-agent
pipelines.

## Quick start

```bash
pip install "agent-coherence[langgraph]"
```

```python
graph = builder.compile(store=CCSStore(strategy="lazy"))
```

**Namespace convention:** `namespace[0]` is the agent identity; `namespace[1:]`
is the artifact scope. Two agents writing to `("planner", "shared")` and
`("reviewer", "shared")` address the same artifact.

**Observability** — pass `on_metric` to measure token savings:

```python
from ccs.adapters import CCSStore, StoreMetricEvent

events = []
store = CCSStore(strategy="lazy", on_metric=events.append)
# each StoreMetricEvent carries: operation, cache_hit, tokens_consumed, tick
```

**Telemetry** — export to OpenTelemetry or LangSmith with one parameter:

```python
store = CCSStore(strategy="lazy", telemetry="opentelemetry")
store = CCSStore(strategy="lazy", telemetry="langsmith")
```

**Graceful degradation** — fall back to a plain dict instead of raising on errors:

```python
store = CCSStore(strategy="lazy", on_error="degrade")
```

See [docs/ccsstore.md](docs/ccsstore.md) for the full guide: namespace convention,
strategies, observability, telemetry, graceful degradation, examples, and API
reference.

### Low-level adapter API

For CrewAI, AutoGen, or custom integrations, use the `before_node` /
`commit_outputs` surface directly:

```python
from ccs.adapters.langgraph import LangGraphAdapter

adapter = LangGraphAdapter(strategy_name="lazy")
for name in ("planner", "researcher", "executor"):
    adapter.register_agent(name)
plan = adapter.register_artifact(name="plan.md", content="v1")

context = adapter.before_node(agent_name="planner", artifact_ids=[plan.id], now_tick=1)
adapter.commit_outputs(
    agent_name="planner",
    writes={plan.id: context[plan.id]["content"] + "\nStep 1"},
    now_tick=2,
)
```

Full example: [`examples/multi_agent_planning.py`](examples/multi_agent_planning.py).

### Running the examples

```bash
python -m examples.langgraph_planner.main   # 4-agent, 75% hit rate, 69% savings
python -m examples.code_review.main          # 3-agent, SHARED state demo
python -m examples.research_pipeline.main    # 4-agent, 3 artifacts, 60% hit rate
```

## Real-workload benchmarks

Measured on real LangGraph `StateGraph` executions using
`GenericFakeChatModel` with no live LLM API calls, so the results are
reproducible in CI. Run them yourself:

```bash
python benchmarks/langgraph_real/bench_planner.py
python benchmarks/langgraph_real/bench_code_review.py
python benchmarks/langgraph_real/bench_high_churn.py
```

| Workload | Agents | Reads:Writes | Hit rate | Baseline tokens | CCSStore tokens | Savings |
|---|---|---|---|---|---|---|
| Planning (read-heavy) | 4 | 12:1 | 75% | 4,160 | 1,301 | **69%** |
| Code review (moderate) | 3 | 8:3 | 60% | 5,320 | 2,835 | **47%** |
| High-churn (write-heavy) | 4 | 8:4 | 50% | 3,250 | 2,317 | **29%** |

### How to read these numbers

**Savings scale with read/write ratio.** That's a property of the protocol, not
an implementation quirk. Every write triggers an invalidation, which forces the
next read to be a miss.

- **Read-heavy workloads (planners, reviewers, summarizers, retrievers): 60–70% savings.**
- **Mixed workloads: 40–55% savings.**
- **Write-heavy workloads: 25–35% savings.**

### Where the paper's 84–95% figures come from

The [arXiv paper](https://arxiv.org/abs/2603.15183) reports 84–95% reduction in
**simulation** under controlled assumptions: sparse reads, high
steps-per-artifact ratios, and low artifact volatility. Those numbers represent
the protocol's theoretical ceiling.

The real-workload numbers above represent what teams see on real LangGraph
graphs today. Both are honest measurements of different things:

| | Simulation (paper) | Real LangGraph (this repo) |
|---|---|---|
| What's measured | Protocol-only token cost | Full graph execution token cost |
| Workload | Synthetic, controlled volatility | Realistic agent patterns |
| Best case | 95% (Planning) | 69% (Planning) |
| Worst case | 84% (High-churn) | 29% (High-churn) |

If you want to reproduce the simulation results from the paper, see
[REPRODUCE.md](REPRODUCE.md).

### What this means for adoption

If your multi-agent workload has a read/write ratio above roughly `3:1`, which
most planning, research, review, and analysis pipelines do, expect 50–70%
savings in production. If your workload is write-heavy, expect 25–35%. Either
way, the integration is a one-line import change.

## What CCSStore is — and isn't

**CCSStore is:**

- A drop-in `BaseStore` replacement for LangGraph
- A way to cut shared-artifact token costs on real multi-agent workloads
- A way to detect stale-read bugs that trace-only tools can't see
- Built on a TLA+-verified MESI protocol

**CCSStore is not:**

- A prompt compiler
- A replacement for LangSmith or Braintrust
- A guaranteed 95% savings tool
- A general-purpose key-value store

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

Five synchronization strategies ship out of the box: `lazy` (default),
`eager`, `lease` (TTL-based), `access_count`, and `broadcast`.

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

## FAQ

### The paper says 84–95%. Why does the README say 47–69%?

Two different measurements, both honest. The paper measures protocol-only
overhead in simulation under controlled assumptions. The README's 47–69% is
what a real team running CCSStore on a real LangGraph graph will measure today
across realistic workloads. Use the 47–69% number for ROI expectations. The
84–95% number describes the protocol's theoretical ceiling under ideal
conditions.

### Why does the high-churn workload only save 29%?

Write-heavy workloads are the protocol's lower bound by design. Every write
triggers invalidation, which forces the next read to be a miss. If your agents
are constantly modifying shared state, fewer reads get to be cache hits.

### Will I see the simulation numbers in production?

Almost certainly not. The simulation isolates the protocol from real-world
factors like LangGraph's framework overhead, prompt construction, and extra
artifact reads. If your workload has a read/write ratio above `3:1`, expect
50–70% in production.

### Can I get higher savings than 69%?

Yes, but it requires architectural changes beyond CCSStore, for example
partial-read APIs so agents fetch only the artifact fragments they need.
CCSStore `v0.2` operates at the whole-artifact level.

## Status

`v0.1` ships the protocol, simulation-based benchmarks, and adapters
for three frameworks. The library is designed to run standalone - the
coordinator, adapters, and strategies are all Apache 2.0 and
production-deployable on your own infrastructure.

Shipped in `v0.2`:

- Production benchmarks on real LangGraph deployments (`benchmarks/langgraph_real/`)
- Telemetry exporters: OpenTelemetry and LangSmith (`ccs.adapters.telemetry`)
- Graceful degradation (`on_error="degrade"`)
- New examples: code review pipeline and research pipeline

Coming next:

- Optimistic-locking strategy for high-contention workloads
- Async coordinator for large agent fleets
- Persistent backend (PostgresStore compatibility)

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
