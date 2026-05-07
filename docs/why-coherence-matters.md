# Why Coherence Matters

Across today's multi-agent frameworks, concurrent writes are treated as a
crash to prevent, not a conflict to resolve. This document collects public
evidence of the gap: framework documentation, unresolved community questions,
and production bug reports. All sources are linked and dated so readers can
verify independently.

---

## 1. The consistency model is unspecified

On December 17, 2025, a backend engineer building an Aerospike-backed
`BaseStore` for LangGraph
[asked the LangChain team](https://forum.langchain.com/t/langgraph-store-batch-semantics-should-putops-be-applied-immediately-or-deferred-deduped-until-end/2545)
a precise question: when `batch()` receives a list of `PutOp` and `GetOp`
operations, do reads later in the list observe earlier writes, or does the
framework treat reads as a pre-batch snapshot?

As of May 2026 — five months later — the thread has no reply from LangChain
staff or community members.

The question is not obscure. It is the definition of an isolation model: does
a store provide read-your-writes consistency, snapshot isolation, or something
else? Without an answer, every `BaseStore` implementer must guess, and two
implementations of the same interface can silently diverge in behavior under
concurrent access.

## 2. The framework treats concurrent writes as unresolvable

LangGraph's
[INVALID_CONCURRENT_GRAPH_UPDATE](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE)
error page states that the framework raises this error because "there is
uncertainty around how to update the internal state" when parallel nodes
write to the same state key.

The recommended workaround is the **reducer pattern**: annotate the state key
with a merge function such as `Annotated[list, operator.add]`, which converts
the key to append-only. This eliminates the error by sidestepping conflict
resolution entirely — concurrent writes are concatenated, not merged.

Two limitations follow. First, append-only is not conflict resolution — if
two agents attempt to update the same item (not append new items), the
reducer produces duplicates rather than a resolved value. Second, even the
append pattern is fragile in practice: community threads report surprising
behavior including exponential duplication and unexpected list nesting when
the reducer interacts with LangGraph's `Command` API.[^1]

[^1]: See [exponential duplication with operator.add](https://forum.langchain.com/t/subject-operator-add-reducer-causes-exponential-duplication-in-annotated-list-state-fields-when-tools-update-state/1546) and [unexpected append behavior](https://forum.langchain.com/t/why-doesn-t-add-reducer-append-properly-to-my-state-list-in-command-update-even-when-i-always-pass-a-list/910).

## 3. The gap surfaced in LangChain's own product

In September 2025, a user
[reported](https://github.com/langchain-ai/deepagents/issues/96) the exact
`INVALID_CONCURRENT_GRAPH_UPDATE` error in Deep Agents — the multi-agent
harness LangChain promotes for production use. Parallel tool nodes writing to
a shared `todos` list triggered the crash.

The issue was closed in January 2026 after a maintainer submitted a fix
(PR [#34637](https://github.com/langchain-ai/langchain/pull/34637)). The fix
added a `_todos_reducer` — the same append-only pattern documented in the
error page. The crash was resolved; the underlying semantic question (what
happens when two agents update the *same* todo) was not.

The crash is gone; the semantic gap remains. The framework prevents the
failure mode without resolving it.

## 4. Users are independently requesting concurrency primitives

On October 30, 2025, a LangGraph user
[filed a feature request](https://forum.langchain.com/t/feature-request-support-concurrency-safe-store-put-operations/2014)
for concurrency-safe `store.put` operations after encountering race
conditions in `get → modify → put` workflows under `langmem`. The proposed
mechanism — "only update a row if the current row value meets the
expectation" — is optimistic locking, the same compare-and-swap primitive
that MVCC systems use.

As of May 2026, the request has no response from LangChain staff.

The pattern is notable because the user arrived at the primitive
independently, from production experience, without referencing database
theory. When users reinvent concurrency control vocabulary from first
principles, it suggests the underlying need is structural rather than
edge-case.

## 5. The pattern across frameworks

The detailed evidence above is drawn from LangGraph because it has the
largest public surface area (documentation, forum, issue tracker). The
underlying pattern — full-context rebroadcasting with no coherence
primitives — recurs across frameworks:

- **CrewAI** passes the complete raw output of upstream tasks to downstream
  consumers via `Task.context`. The framework's internal
  [`aggregate_raw_outputs_from_tasks`](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/src/crewai/crew.py)
  helper joins unmodified `TaskOutput.raw` strings, discarding any structured
  or Pydantic output. Downstream tasks cannot access typed fields from
  upstream results without manual templating
  ([Issue #1977](https://github.com/crewAIInc/crewAI/issues/1977)).
  The official docs confirm that task output is
  [relayed into the next task automatically](https://docs.crewai.com/en/concepts/tasks).

- **AutoGen** uses a shared-topic pub/sub model in its
  [GroupChat](https://microsoft.github.io/autogen/stable//user-guide/core-user-guide/design-patterns/group-chat.html)
  pattern: all participants subscribe to the same message thread, and a
  Group Chat Manager selects the next speaker upon receiving each message.
  The only context-management option is `BufferedChatCompletionContext` — a
  truncation window, not selective sharing or invalidation.

- **Claude Agent SDK** delegates multi-agent coordination entirely to the
  integrator. Its sandbox model provides isolated execution environments but
  no shared-state primitives, leaving coordination to external tooling.

The frameworks differ in *how* they handle the gap. LangGraph errors when
concurrent writes arise; CrewAI and AutoGen avoid the failure mode by
enforcing sequential execution (task DAGs and turn-taking respectively);
Claude Agent SDK delegates coordination to the integrator. None resolves the
underlying conflict — they prevent or sidestep it. In all cases, the default
context-passing mechanism is full rebroadcasting: correct (no stale reads)
but expensive, and scaling poorly as agent count or shared state size grows.

## 6. Open questions

Several questions remain unanswered by any framework or library:

- **What isolation level do multi-agent workloads actually need?** Read-your-writes may suffice for most; some may need snapshot isolation or serializable access. The answer likely varies by workload shape.
- **Is coherence worth its coordination cost for small agent counts?** At 2–3 agents with small shared state, full rebroadcasting may be cheaper than maintaining coherence metadata. The crossover point is not well-characterized.
- **How should coherence interact with agent memory systems?** Long-term memory (e.g., `langmem`) and ephemeral shared state have different consistency requirements. Whether they should share a coherence model or remain separate is an open design question.

---

*Last verified: May 7, 2026. All URLs were confirmed live and all claims
checked against current source material on this date.*
