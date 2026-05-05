# State Transitions Log — Proposal

**Status:** Implemented — shipped in v0.3  
**Validation gate:** 2+ discovery contacts confirm the schema is useful by 2026-05-16  
**Implementation:** `CCSStore(state_log=cb)` — see [docs/ccsstore.md](../ccsstore.md#state-transitions-log)

---

## Overview

The state transitions log is an opt-in, structured stream of MESI state changes emitted
by `CCSStore`. Each entry records one stable-state transition for one agent/artifact pair,
together with the coordinator operation that triggered it.

The log is intended for external tool builders — debuggers, visualizers, audit pipelines —
who need to correlate agent behavior with coherence state changes without coupling their
tools to CCS internals. The primary use case is diagnosing LangGraph cycle failures by
tracing which agents held stale (INVALID) entries at the time of a fault.

---

## Schema

Each log entry is a flat dict emitted as the payload to the user-provided `state_log`
callable. Keys:

| Field | Type | Description |
|-------|------|-------------|
| `tick` | `int` | Simulation tick counter when the transition occurred. Always-incrementing within a `CCSStore` session; starts at 0. For real-execution use (non-simulation), this is a monotonic operation counter, not wall time. |
| `artifact_id` | `str` | UUID of the artifact whose per-agent state changed. |
| `agent_id` | `str` | UUID of the agent whose state changed. |
| `agent_name` | `str \| null` | Human-readable display name for the agent, if available via a registry name mapping; `null` otherwise. See [Agent Name Resolution](#agent-name-resolution). |
| `from_state` | `str` | Previous stable `MESIState` value: `"MODIFIED"`, `"EXCLUSIVE"`, `"SHARED"`, or `"INVALID"`. For a newly registered agent, the implicit prior state is `"INVALID"`. |
| `to_state` | `str` | New stable `MESIState` value after the transition. |
| `trigger` | `str` | Coordinator operation that caused the transition. One of the six values in [Trigger Vocabulary](#trigger-vocabulary). |
| `version` | `int` | Artifact version number at the moment of the transition. |

---

## Trigger Vocabulary

The `trigger` field is set by the coordinator method that calls `registry.set_agent_state`.
All valid values:

| Value | Coordinator method | When it fires |
|-------|-------------------|---------------|
| `"register"` | `register_artifact` | Initial artifact registration; the registering agent receives EXCLUSIVE |
| `"fetch"` | `fetch` | Fetch grant; requesting agent transitions to SHARED or EXCLUSIVE |
| `"write"` | `write` | Write request; peers are invalidated (→ INVALID), requesting agent receives EXCLUSIVE |
| `"commit"` | `commit` | Write commit; peers are invalidated (→ INVALID), committing agent transitions to MODIFIED |
| `"invalidate"` | `invalidate` | Explicit invalidation signal received; agent transitions to INVALID |
| `"timeout"` | `enforce_transient_timeouts` | Transient state timeout; agent force-invalidated (→ INVALID) |

---

## Hook Point

The log emitter sits in `coordinator/registry.py:set_agent_state`. The implementation
must read `from_state` before applying the update, then emit the payload.

The `trigger` parameter does not currently exist on `set_agent_state` — adding it requires
updating all call sites in `coordinator/service.py` (~9 direct calls across 5 methods).
This is a planned implementation change; the spec is the contract the implementation aligns to.

```python
# Directional sketch — not implementation specification
def set_agent_state(
    self,
    artifact_id: UUID,
    agent_id: UUID,
    state: MESIState,
    *,
    trigger: str = "unknown",
) -> None:
    from_state = self._records[artifact_id].state_by_agent.get(
        agent_id, MESIState.INVALID
    )
    self._records[artifact_id].state_by_agent[agent_id] = state
    if self._state_log is not None:
        version = self._records[artifact_id].artifact.version
        self._state_log({
            "tick": self._tick,
            "artifact_id": str(artifact_id),
            "agent_id": str(agent_id),
            "agent_name": self._agent_names.get(agent_id) if self._agent_names else None,
            "from_state": from_state.name,
            "to_state": state.name,
            "trigger": trigger,
            "version": version,
        })
```

The `_state_log` callable and `_agent_names` mapping are stored on the registry instance,
injected from `CCSStore` at construction time. The `_tick` is the coordinator's current
operation counter.

---

## Opt-In Interface

The `state_log` parameter on `CCSStore` accepts any `Callable[[dict], None]`.
Default: `None` (no-op, zero overhead).

```python
# Collect entries in memory (testing, short sessions)
log_entries: list[dict] = []
store = CCSStore(strategy="lazy", state_log=log_entries.append)

# Write to JSONL file (long sessions, external tools)
import json
with open("transitions.jsonl", "w") as f:
    store = CCSStore(
        strategy="lazy",
        state_log=lambda entry: f.write(json.dumps(entry) + "\n"),
    )

# Structured logging (production integration)
import logging
logger = logging.getLogger("ccs.transitions")
store = CCSStore(
    strategy="lazy",
    state_log=lambda entry: logger.debug("transition", extra=entry),
)
```

---

## Example Output

The following JSONL block shows a 4-agent planning pipeline: planner writes the plan
(fetches exclusive, commits), three readers fetch shared copies, then planner invalidates
all peers on a second write.

```jsonl
{"tick": 1, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "aa00-...", "agent_name": "planner", "from_state": "INVALID", "to_state": "EXCLUSIVE", "trigger": "register", "version": 0}
{"tick": 2, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "bb11-...", "agent_name": "researcher", "from_state": "INVALID", "to_state": "SHARED", "trigger": "fetch", "version": 1}
{"tick": 2, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "cc22-...", "agent_name": "executor", "from_state": "INVALID", "to_state": "SHARED", "trigger": "fetch", "version": 1}
{"tick": 2, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "dd33-...", "agent_name": "reviewer", "from_state": "INVALID", "to_state": "SHARED", "trigger": "fetch", "version": 1}
{"tick": 3, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "aa00-...", "agent_name": "planner", "from_state": "EXCLUSIVE", "to_state": "MODIFIED", "trigger": "commit", "version": 1}
{"tick": 4, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "bb11-...", "agent_name": "researcher", "from_state": "SHARED", "to_state": "INVALID", "trigger": "write", "version": 2}
{"tick": 4, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "cc22-...", "agent_name": "executor", "from_state": "SHARED", "to_state": "INVALID", "trigger": "write", "version": 2}
{"tick": 4, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "dd33-...", "agent_name": "reviewer", "from_state": "SHARED", "to_state": "INVALID", "trigger": "write", "version": 2}
{"tick": 4, "artifact_id": "a1b2c3d4-0000-0000-0000-000000000001", "agent_id": "aa00-...", "agent_name": "planner", "from_state": "MODIFIED", "to_state": "EXCLUSIVE", "trigger": "write", "version": 2}
```

Reading this trace: ticks 2–3 show a clean read-then-commit sequence. Tick 4 shows the
planner reclaiming EXCLUSIVE for a second write, simultaneously invalidating all three
SHARED readers. Any agent that attempts a read after tick 4 will fetch fresh content
(next INVALID → SHARED fetch).

---

## Intended Use Cases

### External debugger integration

Correlate MESI state transitions with LangGraph node execution order to diagnose cycle
failures caused by stale reads. A cycle failure where an agent reads a plan that a
co-running agent just invalidated will show up as a `trigger: "write"` → `to_state:
"INVALID"` entry for the reading agent, followed by no subsequent `trigger: "fetch"` for
that agent before the failure.

### State timeline visualization

Render a per-agent, per-artifact timeline from the JSONL log. Each row is an agent;
each column is a tick; each cell is the agent's MESI state for a given artifact. Useful
for post-hoc analysis of multi-agent pipelines without modifying application code.

### Coherence audit

Verify that no agent reads a MODIFIED artifact without an intervening fetch. A compliant
log will never show a `to_state: "MODIFIED"` entry followed by another agent's access
without a `trigger: "fetch"` in between.

---

## Open Questions

### Agent Name Resolution

`set_agent_state` currently receives `agent_id: UUID` only. The registry does not store
a name-to-UUID mapping. For `agent_name` to be non-null, either:

1. `CCSStore` accepts an optional `agent_names: dict[UUID, str]` mapping at construction
   (simple, explicit)
2. `AgentRuntime` registers its name with the coordinator at startup (automatic, couples
   more layers)

Option 1 is preferred for a first implementation — lower coupling, compatible with the
opt-in philosophy of the log itself. If `agent_names` is not provided, `agent_name` is
always `null`.

### Transient State Coverage

This spec covers stable-state transitions only (via `set_agent_state`). Capturing
in-flight transient states (ISG, IED, EIA, SIA, MWB, MSA) requires a separate hook in
`set_agent_transient` / `clear_agent_transient`. Transient coverage is useful for
diagnosing races and lock contention but adds complexity. Deferred pending validation
that the stable-state log alone satisfies the debugger use case.

### Performance

If the `state_log` callable is slow (e.g., synchronous disk I/O on every transition),
it adds latency to every `set_agent_state` call — which is on the critical path of
`fetch`, `write`, and `commit`. Users with high-throughput workloads should use a
non-blocking callback (e.g., write to an in-memory queue; drain asynchronously). The
spec makes no performance guarantee about the callable execution context.

### Replay Tooling

A natural extension: replay a captured JSONL log to reconstruct the full coherence state
at any tick, enabling step-through debugging of LangGraph cycle failures. This requires
deterministic tick assignment (currently sequential per-operation, which suffices) and a
replay API that can hydrate a registry from a log file. Listed here as a potential future
extension; not in scope for the initial implementation or this validation pass.

---

## Validation Gate

This spec is shared with the cycle-debugger contact (and any other discovery contacts
interested in external tooling) as a lightweight validation artifact.

**Proceed to implementation if:** 2+ independent contacts confirm the schema fields and
trigger vocabulary cover their actual friction point by 2026-05-16.

**Defer if:** fewer than 2 contacts validate, or feedback requires significant schema
changes. In that case, revise the spec and re-validate before building.
