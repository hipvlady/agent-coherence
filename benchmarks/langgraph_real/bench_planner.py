"""Real LangGraph benchmark — read-heavy planner workload.

4-agent graph: Planner → Researcher → Executor → Reviewer.
Planner writes a plan artifact once (LLM-generated content).
Researcher, Executor, Reviewer each read the plan 4× (simulating multi-pass work).

Expected behaviour:
  Each downstream agent's first read: cache miss (INVALID → SHARED).
  Reads 2-4 per agent: cache hits (SHARED persists until next write).
  3 misses + 9 hits = 75% cache hit rate → ~70%+ token reduction.

Run:
  python benchmarks/langgraph_real/bench_planner.py
"""

from __future__ import annotations

from typing import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.config import get_store as lg_get_store
from langgraph.graph import END, START, StateGraph

from benchmarks.langgraph_real._scaffold import (
    ComparisonResult,
    make_fake_llm,
    print_comparison,
    run_comparison,
    save_results,
)

PLAN_KEY = "plan"
PLAN_NAMESPACE_SCOPE = "shared"
NUM_READS_PER_AGENT = 4
DOWNSTREAM_AGENTS = ["researcher", "executor", "reviewer"]
RESPONSE_TOKENS = 320


class GraphState(TypedDict):
    log: list[str]


def _build_graph(store) -> "CompiledStateGraph":
    llm = make_fake_llm(response_tokens=RESPONSE_TOKENS)

    def planner_node(state: GraphState) -> dict:
        s = lg_get_store()
        response = llm.invoke([HumanMessage(content="Generate a Q2 research plan.")])
        s.put(("planner", PLAN_NAMESPACE_SCOPE), PLAN_KEY, {"content": response.content})
        return {"log": [*state["log"], "planner: wrote plan"]}

    def _make_reader(agent_name: str):
        def node(state: GraphState) -> dict:
            s = lg_get_store()
            for _ in range(NUM_READS_PER_AGENT):
                item = s.get((agent_name, PLAN_NAMESPACE_SCOPE), PLAN_KEY)
                assert item is not None
            return {"log": [*state["log"], f"{agent_name}: read plan {NUM_READS_PER_AGENT}×"]}
        node.__name__ = f"{agent_name}_node"
        return node

    builder = StateGraph(GraphState)
    builder.add_node("planner", planner_node)
    for name in DOWNSTREAM_AGENTS:
        builder.add_node(name, _make_reader(name))

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "researcher")
    builder.add_edge("researcher", "executor")
    builder.add_edge("executor", "reviewer")
    builder.add_edge("reviewer", END)

    return builder.compile(store=store)


def run() -> ComparisonResult:
    result = run_comparison(
        build_graph_fn=_build_graph,
        initial_state={"log": []},
        content_tokens=RESPONSE_TOKENS,
        label="4-agent planning pipeline (read-heavy)",
    )
    print_comparison(result)
    path = save_results(result)
    print(f"  Results saved to: {path}")
    print()
    return result


if __name__ == "__main__":
    run()
