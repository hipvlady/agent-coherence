"""4-agent LangGraph integration demo for CCSStore.

Workload: Planner writes a shared plan once. Then Researcher, Executor, and
Reviewer each read the plan 4 times (simulating multiple passes over shared
context). Total: 1 write + 12 reads across 3 agents.

Cache behaviour with lazy strategy:
  Each downstream agent's first read is a cache miss (INVALID → SHARED).
  Reads 2-4 per agent are cache hits (SHARED state persists until next write).
  3 misses + 9 hits = 75% cache hit rate.

Token accounting:
  Cache miss: tokens_consumed = full content size (content fetched from coordinator)
  Cache hit:  tokens_consumed = 1 (no content transfer; already in local cache)

Run:
  python -m examples.langgraph_planner.main
"""
# ruff: noqa: F401

from __future__ import annotations

from typing import TypedDict

from langgraph.config import get_store as lg_get_store
from langgraph.graph import END, START, StateGraph

from ccs.adapters.ccsstore import CCSStore

# ---------------------------------------------------------------------------
# Shared artifact content  (~100 tokens to make the numbers meaningful)
# ---------------------------------------------------------------------------

PLAN_CONTENT = {
    "title": "Q2 Research Initiative",
    "objectives": [
        "Benchmark coherence protocol against baseline on 4-agent planning workload",
        "Verify MESI state transitions under concurrent write patterns",
        "Collect token consumption metrics across three strategy variants",
    ],
    "milestones": {
        "week_1": "Set up evaluation harness and baseline measurements",
        "week_2": "Run coherence protocol benchmarks and collect raw metrics",
        "week_3": "Statistical analysis and comparison report",
    },
    "owner": "planner",
    "status": "active",
}

PLAN_KEY = "plan"
PLAN_NAMESPACE_SCOPE = "shared"  # artifact scope — same for all agents

NUM_READS_PER_AGENT = 4  # reads 2-4 are cache hits
DOWNSTREAM_AGENTS = ["researcher", "executor", "reviewer"]


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    log: list[str]


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def planner_node(state: GraphState) -> dict:
    """Planner writes the shared plan artifact once."""
    store: CCSStore = lg_get_store()  # type: ignore[assignment]
    store.put(("planner", PLAN_NAMESPACE_SCOPE), PLAN_KEY, PLAN_CONTENT)
    return {"log": [*state["log"], "planner: wrote plan"]}


def _make_reader_node(agent_name: str):
    """Factory: node that reads the shared plan NUM_READS_PER_AGENT times."""

    def node(state: GraphState) -> dict:
        store: CCSStore = lg_get_store()  # type: ignore[assignment]
        for pass_num in range(1, NUM_READS_PER_AGENT + 1):
            item = store.get((agent_name, PLAN_NAMESPACE_SCOPE), PLAN_KEY)
            assert item is not None, f"{agent_name}: plan missing on pass {pass_num}"
        return {"log": [*state["log"], f"{agent_name}: read plan {NUM_READS_PER_AGENT}×"]}

    node.__name__ = f"{agent_name}_node"
    return node


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(store: CCSStore) -> "CompiledStateGraph":
    builder = StateGraph(GraphState)

    builder.add_node("planner", planner_node)
    for name in DOWNSTREAM_AGENTS:
        builder.add_node(name, _make_reader_node(name))

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "executor")
    builder.add_edge("executor", "reviewer")
    builder.add_edge("reviewer", END)

    return builder.compile(store=store)


# ---------------------------------------------------------------------------
# Main: run and print comparison table
# ---------------------------------------------------------------------------

def run() -> None:
    store = CCSStore(strategy="lazy", benchmark=True)
    graph = build_graph(store)

    final_state = graph.invoke({"log": []})

    print()
    print("Example: 4-agent planning pipeline")
    print()
    for entry in final_state["log"]:
        print(f"  {entry}")
    print()
    store.print_benchmark_summary()


if __name__ == "__main__":
    run()

# Comparing notes on multi-agent coherence?
# https://github.com/hipvlady/agent-coherence/discussions
