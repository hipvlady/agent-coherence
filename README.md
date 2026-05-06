# agent-coherence

When two agents share state, one of them is usually reading a stale copy. `agent-coherence` makes that visible.

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

On a stale read, `agent-coherence` surfaces the conflict in the run log instead of letting the agent silently work from outdated context.

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

- 📄 [Paper on arXiv (2603.15183)](https://arxiv.org/abs/2603.15183) — formal protocol, TLA+ verification, simulation results
- 📊 [Real benchmarks](#real-workload-benchmarks) — measured on actual LangGraph graphs
- 🔧 [User guide](docs/guide.md) — strategies, telemetry, examples

---

## How it works

Each shared artifact is cached locally per agent and reads serve from the local cache when
that copy is fresh. Writes commit to a coordinator, which sends lightweight invalidation
signals (~12 tokens) to peers so the next read fetches the new version instead of rebroadcasting
the full artifact. Consistency is single-writer-multiple-reader per artifact with bounded
staleness — peers re-fetch on next read.

Five synchronization strategies ship out of the box: `lazy` (default), `eager`, `lease`
(TTL-based), `access_count`, and `broadcast`.

## Quick start

**Namespace convention:** `namespace[0]` is the agent identity; `namespace[1:]` is the artifact
scope. Two agents writing to `("planner", "shared")` and `("reviewer", "shared")` address
the same artifact.

See [docs/guide.md](docs/guide.md) for the full guide: namespace convention,
strategies, observability, telemetry, graceful degradation, examples, and API reference.

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

Savings scale with read/write ratio:

| Workload | Agents | Reads:Writes | Hit rate | Baseline tokens | CCSStore tokens | Savings |
|---|---|---|---|---|---|---|
| Planning (read-heavy) | 4 | 12:1 | 75% | 4,160 | 1,301 | **69%** |
| Code review (moderate) | 3 | 8:3 | 60% | 5,320 | 2,835 | **47%** |
| High-churn (write-heavy) | 4 | 8:4 | 50% | 3,250 | 2,317 | **29%** |

For protocol-only simulation methodology, see [REPRODUCE.md](REPRODUCE.md).

### Benchmark your own workload

```bash
pip install "agent-coherence[langgraph,benchmark]"
ccs-benchmark --graph path/to/your_graph.py:build_graph
```

The factory must accept a single `store` argument and return a compiled LangGraph graph
(`builder.compile(store=store)`). The CLI runs the graph once and prints a token savings
summary. Use `--initial-state '{"key": "value"}'` to pass a custom input dict.

## Architecture

- **Protocol** (`ccs.core`, `ccs.strategies`) — coherence state machine and synchronization
  strategies; no framework dependencies.
- **Coordinator** (`ccs.coordinator`) — authority service tracking directory state and
  publishing invalidations; runs in-process or out-of-process.
- **Adapters** (`ccs.adapters`) — framework integrations for LangGraph, CrewAI, and AutoGen;
  ~100 lines each.
- **Event bus** (`ccs.bus`) — pluggable transport for invalidation signals; in-memory by
  default, swap in Redis, Kafka, NATS, or gRPC streams for production.

## Status

`v0.4` released. See [releases](https://github.com/hipvlady/agent-coherence/releases) for
full history. Alpha — APIs may change before `v1.0`.

**What's new in v0.4:** sequence-numbered event streams and `validate_log` for replay
correctness checks.

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
