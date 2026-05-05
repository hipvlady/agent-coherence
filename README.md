# agent-coherence

CCSStore is a drop-in token optimization layer for multi-agent LangGraph systems.
It cuts shared-artifact token costs on realistic workloads — via MESI cache coherence,
one import change.

[![CI](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml/badge.svg)](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agent-coherence)](https://pypi.org/project/agent-coherence/)
[![arXiv](https://img.shields.io/badge/arXiv-2603.15183-b31b1b)](https://arxiv.org/abs/2603.15183)

```bash
pip install "agent-coherence[langgraph]"
```

```python
# Before
from langgraph.store.memory import InMemoryStore
store = InMemoryStore()

# After — one import change, no other code changes
from ccs.adapters import CCSStore
store = CCSStore(strategy="lazy")
```

```
$ python -m examples.shared_codebase.main

Example: 4-agent shared-codebase code review

  style_reviewer: 8 files scanned, 4 re-read, findings written
  security_reviewer: 8 files scanned, 4 re-read, findings written
  architecture_reviewer: 8 files scanned, 4 re-read, findings written
  synthesizer: 3 findings read, context re-read (12 issues total)

  CCSStore Benchmark Summary
  ──────────────────────────────────────
  Baseline tokens (no cache):     44702
  CCSStore tokens:                27882
  Tokens saved:                   16820
  Token reduction:                37.6%
  Cache hit rate:                35.3%  (51 get ops)
```

Saving 16,820 tokens at $3/MTok = **$0.050 per run**. At 1,000 runs/day: **$18K/year** on one
codebase-review workload.

> **Baseline:** tokens you would pay if every agent re-read every shared artifact from scratch —
> equivalent to a graph without cross-agent caching. This is what `InMemoryStore` effectively does.

> **ROI floor:** At 150 runs/day of a codebase-review-class workload, savings exceed **$3K/year** —
> a defensible 30× return on a one-line integration. At 3,000 runs/day the math reaches enterprise
> scale. For teams running small-artifact pipelines at under 500 runs/day, savings will be
> proportionally smaller.

- 📄 [Paper on arXiv (2603.15183)](https://arxiv.org/abs/2603.15183) — formal protocol, TLA+ verification, simulation results
- 📊 [Real benchmarks](#real-workload-benchmarks) — measured on actual LangGraph graphs
- 🔧 [User guide](docs/ccsstore.md) — strategies, telemetry, examples

---

## How it works

When multiple agents share working context — a plan, a codebase, a research document — most
orchestration frameworks rebroadcast the full artifact to every agent on every step.
On workloads with four or more agents and non-trivial artifacts, synchronization tokens
dominate total cost.

CCSStore solves this with the same approach multi-core CPUs have used since 1984: MESI cache
coherence. Each shared artifact sits in one of four states per agent — **Modified**,
**Exclusive**, **Shared**, or **Invalid**. Agents read from local cache when valid; only
invalid cache entries trigger a network fetch.

- **Reads** hit the local cache at zero token cost when the artifact hasn't changed.
- **Writes** commit to a coordinator, which sends lightweight invalidation signals (~12 tokens)
  to peers instead of rebroadcasting the full artifact.
- **Consistency** is single-writer-multiple-reader per artifact, with bounded staleness — peers
  re-fetch on next read.

Five synchronization strategies ship out of the box: `lazy` (default), `eager`, `lease`
(TTL-based), `access_count`, and `broadcast`.

## Quick start

**Namespace convention:** `namespace[0]` is the agent identity; `namespace[1:]` is the artifact
scope. Two agents writing to `("planner", "shared")` and `("reviewer", "shared")` address
the same artifact.

**Inline benchmark mode** — measure token savings on your own workload without any external
tooling:

```python
store = CCSStore(strategy="lazy", benchmark=True)
# ... run your graph ...
store.print_benchmark_summary()
```

**Observability** — pass `on_metric` to receive per-operation events:

```python
from ccs.adapters import CCSStore, StoreMetricEvent

events = []
store = CCSStore(strategy="lazy", on_metric=events.append)
# each StoreMetricEvent carries: operation, cache_hit, tokens_consumed, tokens_saved_estimate, tick
```

**State transitions log** — stream every MESI state change to an external tool:

```python
log = []
store = CCSStore(strategy="lazy", state_log=log.append)
# each entry: {tick, artifact_id, agent_id, agent_name, from_state, to_state, trigger, version}
```

Write to JSONL for offline analysis or pass any callable. `state_log=None` (default) adds zero overhead.

**Telemetry** — export to OpenTelemetry or LangSmith with one parameter:

```python
store = CCSStore(strategy="lazy", telemetry="opentelemetry")
store = CCSStore(strategy="lazy", telemetry="langsmith")
```

**Graceful degradation** — fall back to a plain dict instead of raising on coherence errors:

```python
store = CCSStore(strategy="lazy", on_error="degrade")
# first degradation emits CoherenceDegradedWarning; store.is_degraded returns True after
```

See [docs/ccsstore.md](docs/ccsstore.md) for the full guide: namespace convention,
strategies, observability, telemetry, graceful degradation, examples, and API reference.

### Low-level adapter API

For CrewAI, AutoGen, or custom integrations, use the `before_node` / `commit_outputs`
surface directly:

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
python -m examples.shared_codebase.main    # 4-agent code review, 16,820 tokens saved, $18K/year
python -m examples.langgraph_planner.main  # 4-agent planning, 74.4% savings — smaller artifact illustration
python -m examples.code_review.main        # 3-agent, SHARED state demo
python -m examples.research_pipeline.main  # 4-agent, 3 artifacts, 60% hit rate
```

## Real-workload benchmarks

Measured on real LangGraph `StateGraph` executions using `GenericFakeChatModel` with no live
LLM API calls, so the results are reproducible in CI. Run them yourself:

```bash
pip install "agent-coherence[langgraph,benchmark]"
make benchmark    # runs all three workloads, prints consolidated table
```

Or run individually:

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

### Benchmark your own workload

```bash
pip install "agent-coherence[langgraph,benchmark]"
ccs-benchmark --graph path/to/your_graph.py:build_graph
```

The factory must accept a single `store` argument and return a compiled LangGraph graph
(`builder.compile(store=store)`). The CLI runs the graph once and prints a token savings
summary. Use `--initial-state '{"key": "value"}'` to pass a custom input dict.

### How to read these numbers

**Savings scale with read/write ratio.** Every write triggers invalidation, which forces the
next read to be a miss.

- **Read-heavy workloads (planners, reviewers, summarizers, retrievers): 60–70% savings.**
- **Mixed workloads: 40–55% savings.**
- **Write-heavy workloads: 25–35% savings.**

### Where the paper's 84–95% figures come from

The [arXiv paper](https://arxiv.org/abs/2603.15183) reports 84–95% reduction in
**simulation** under controlled assumptions: sparse reads, high steps-per-artifact ratios,
and low artifact volatility. Those numbers represent the protocol's theoretical ceiling.

The real-workload numbers above represent what teams see on real LangGraph graphs today.
Both are honest measurements of different things:

| | Simulation (paper) | Real LangGraph (this repo) |
|---|---|---|
| What's measured | Protocol-only token cost | Full graph execution token cost |
| Workload | Synthetic, controlled volatility | Realistic agent patterns |
| Best case | 95% (Planning) | 69% (Planning) |
| Worst case | 84% (High-churn) | 29% (High-churn) |

If you want to reproduce the simulation results from the paper, see
[REPRODUCE.md](REPRODUCE.md).

### What this means for adoption

If your multi-agent workload has a read/write ratio above roughly `3:1` — which most
planning, research, review, and analysis pipelines do — expect 50–70% savings in
production. If your workload is write-heavy, expect 25–35%. Either way, the integration
is a one-line import change.

## What CCSStore is — and isn't

**CCSStore is:**

- A drop-in `BaseStore` replacement for LangGraph
- A token optimization layer for multi-agent workloads built on MESI cache coherence
- A way to detect stale-read bugs that trace-only tools can't see
- Built on a TLA+-verified protocol

Orchestration frameworks decide which agents run; agent-coherence decides what version they read.

**CCSStore is not:**

- A prompt compiler
- A replacement for LangSmith or Braintrust
- A guaranteed 95% savings tool
- A general-purpose key-value store

## Architecture

`agent-coherence` is structured as four composable layers:

- **Protocol** (`ccs.core`, `ccs.strategies`) — MESI state machine and synchronization
  strategies. No framework dependencies.
- **Coordinator** (`ccs.coordinator`) — Authority service tracking directory state and
  publishing invalidations. Runs in-process or out-of-process.
- **Event bus** (`ccs.bus`) — Pluggable transport for invalidation signals. Ships with an
  in-memory bus; production deployments can swap in Redis, Kafka, NATS, or gRPC streams.
- **Adapters** (`ccs.adapters`) — Framework integrations for LangGraph, CrewAI, and AutoGen.
  Each ~100 lines; adding a new framework is straightforward.

Each layer is independently useful and independently replaceable.

## Guarantees

The protocol is specified in TLA+ and model-checked with TLC. Verified properties:

- **Safety** — Single-writer-multiple-reader per artifact and monotonic versions
- **Token Coherence Theorem** — Lower bound on savings vs. broadcast for any workload with
  write probability < 1
- **Liveness** — Every invalidated cache eventually reaches a valid state

See Section 6 of [the paper](https://arxiv.org/abs/2603.15183) for the formal model and
proof details.

## Why not just...

**...use mem0 or Letta?** Retrieval-based memory does not solve concurrency. Two agents
retrieving the same artifact and writing independently will clobber each other.
`agent-coherence` is a coherence *protocol*, not a memory store — it composes with any
retrieval backend.

**...use LangGraph's `BaseStore`?** `BaseStore` provides persistence, not concurrency
safety. The LangGraph docs explicitly warn users to handle concurrent writes themselves.
`agent-coherence` is the layer that does that.

**...use A2A?** A2A is the transport layer — how agents send tasks to each other.
`agent-coherence` is the artifact coherence layer — how agents share state *while* they
work. They compose.

**...use Anthropic / OpenAI prompt caching?** Provider-side caching reduces per-agent prompt
overhead but does not address inter-agent artifact synchronization. The two are
complementary: prompt caching keeps the prefix cheap; coherence keeps the shared artifacts
lean.

## FAQ

### The paper says 84–95%. Why does the benchmark table show 29–69%?

Two different measurements, both honest. The paper measures protocol-only overhead in
simulation under controlled assumptions. The 29–69% range is what you measure running
CCSStore on a real LangGraph graph. The dollar story in the headline uses absolute token
savings — percentage depends on read/write ratio, absolute savings depend on artifact size.
Use the benchmark table for ROI expectations on your workload type. The 84–95% describes
the protocol's theoretical ceiling under ideal conditions.

### Why does the high-churn workload only save 29%?

Write-heavy workloads are the protocol's lower bound by design. Every write triggers
invalidation, which forces the next read to be a miss.

### Will I see the simulation numbers in production?

Almost certainly not. The simulation isolates the protocol from real-world factors like
LangGraph's framework overhead, prompt construction, and extra artifact reads. If your
workload has a read/write ratio above `3:1`, expect 50–70% in production.

### Can I get higher percentage savings than the benchmark table shows?

Yes. The benchmark table measures realistic agent patterns. Under more read-heavy conditions
(larger artifacts, more agents, fewer writes) percentage savings increase. For higher
absolute savings, use larger shared artifacts — savings scale linearly with artifact size.
CCSStore `v0.2` operates at the whole-artifact level; partial-read APIs would unlock
additional savings.

## Status

`v0.3` ships the state transitions log, a reproducible benchmark harness, and the
`ccs-benchmark` CLI.

Shipped in `v0.3`:

- **State transitions log** — `CCSStore(state_log=cb)` streams every MESI state change
  as a structured dict; zero overhead when unused
- **Reproducible benchmark harness** — `make benchmark` runs all three real-workload
  benchmarks in one command and guards against README number drift in CI
- **`ccs-benchmark` CLI** — benchmark custom LangGraph workloads without writing test code

Shipped in `v0.2`:

- **Inline benchmark mode** — `CCSStore(benchmark=True)` + `print_benchmark_summary()`
- **Degradation visibility** — `CoherenceDegradedWarning`, `is_degraded`, `degradation_count`
- **Expanded telemetry** — OTel: tokens saved, cache hit/miss counters, degraded-mode gauge;
  LangSmith: per-run `token_reduction_pct`, `cache_hit_rate`, `tokens_saved_estimate`
- **Shared-codebase example** — 4-agent code review pipeline with benchmark output
- Production benchmarks on real LangGraph deployments (`benchmarks/langgraph_real/`)
- Telemetry exporters: OpenTelemetry and LangSmith (`ccs.adapters.telemetry`)
- Graceful degradation (`on_error="degrade"`)

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
