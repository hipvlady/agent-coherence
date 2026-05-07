# How agent-coherence Fills the Gap

This document describes one approach to the coherence gap documented in
[Why Coherence Matters](why-coherence-matters.md). Other approaches are
possible: CRDT-based merge for collaborative artifacts where concurrent
writes are semantically composable, MVCC-style snapshot isolation for
parallel branches where subagents need isolated reasoning before
reconciliation, or framework-level solutions at the storage or orchestration
layer. MESI suits read-heavy shared context with localized writes — the
dominant pattern across the frameworks documented in the companion piece.

---

## The approach

The [`agent-coherence`](https://github.com/hipvlady/agent-coherence) library
provides coherence primitives for multi-agent shared state: version tracking,
invalidation signaling, and configurable synchronization strategies (eager,
lazy, lease-based). It implements a MESI-derived protocol adapted from CPU
cache coherence — a domain where the "multiple readers, shared mutable state"
problem has been solved for decades.

For LangGraph specifically, `agent-coherence` ships a drop-in `BaseStore`
replacement (`CCSStore`) that adds coherence semantics — swap the store
import and the protocol handles the rest. Agents that hold current data skip re-reads; agents that hold
stale data are notified. The protocol enforces single-writer exclusivity and
monotonic versioning as invariants, not conventions.

## What this addresses

| Gap (from [Why Coherence Matters](why-coherence-matters.md)) | How agent-coherence responds |
|---|---|
| No defined isolation model (Section 1) | MESI states provide explicit read/write ownership semantics per agent per artifact |
| Concurrent writes unresolvable (Section 2) | Single-writer exclusivity prevents concurrent writes at the protocol level |
| Reducer pattern is append-only (Section 2) | Conflict is avoided by grant, not resolved by merge — only one agent holds write permission at a time |
| Users requesting optimistic locking (Section 4) | Version-tracked artifacts with monotonic versioning; stale writes are rejected |
| Full-context rebroadcasting (Section 5) | Invalidation signals notify agents of changes; only stale caches re-fetch |

## What this does not address

The [open questions](why-coherence-matters.md#6-open-questions) in the
evidence document apply here too:

- The coordination-cost crossover point for small agent counts is not yet
  well-characterized.
- Interaction with long-term memory systems (e.g., `langmem`) is unexplored.
- The right isolation level for different workload shapes remains an open
  research question.

---

See the [User Guide](guide.md) for installation, configuration, and examples.
