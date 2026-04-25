"""Real LangGraph benchmark — write-heavy high-churn workload.

4-agent pipeline where each agent reads the shared artifact twice (analysis passes)
then overwrites it. Each write invalidates the next agent's SHARED cache entry,
forcing a miss on the first read of the next round.

Hit rate behaviour:
  First read per agent per cycle: cache miss (previous agent wrote → INVALID).
  Second read per agent per cycle: cache hit (no write between the two reads).
  4 agents × (1 miss + 1 hit) = 50% hit rate — lower than read-heavy (75%),
  reflecting the elevated write frequency.

Run:
  python benchmarks/langgraph_real/bench_high_churn.py
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

ARTIFACT_KEY = "shared_state"
SCOPE = "shared"
RESPONSE_TOKENS = 250
AGENTS = ["agent_a", "agent_b", "agent_c", "agent_d"]
READS_BEFORE_WRITE = 2  # read twice before overwriting; 2nd read is always a hit


class GraphState(TypedDict):
    log: list[str]


def _make_churn_node(agent_name: str):
    llm = make_fake_llm(response_tokens=RESPONSE_TOKENS)

    def node(state: GraphState) -> dict:
        s = lg_get_store()
        # Two reads: first is a miss (peer wrote), second is a hit (no write in between)
        for _ in range(READS_BEFORE_WRITE):
            item = s.get((agent_name, SCOPE), ARTIFACT_KEY)
            assert item is not None
        # Write invalidates all other agents' SHARED copies
        resp = llm.invoke([HumanMessage(content=f"{agent_name}: update.")])
        s.put((agent_name, SCOPE), ARTIFACT_KEY, {"state": resp.content, "writer": agent_name})
        return {"log": [*state["log"], f"{agent_name}: read×{READS_BEFORE_WRITE}+write"]}

    node.__name__ = f"{agent_name}_node"
    return node


def _build_graph(store) -> "CompiledStateGraph":
    builder = StateGraph(GraphState)
    for name in AGENTS:
        builder.add_node(name, _make_churn_node(name))
    builder.add_edge(START, AGENTS[0])
    for i in range(len(AGENTS) - 1):
        builder.add_edge(AGENTS[i], AGENTS[i + 1])
    builder.add_edge(AGENTS[-1], END)
    return builder.compile(store=store)


def _build_graph_with_setup(store) -> "CompiledStateGraph":
    llm = make_fake_llm(response_tokens=RESPONSE_TOKENS)
    resp = llm.invoke([HumanMessage(content="Initial shared state.")])
    store.put(("setup", SCOPE), ARTIFACT_KEY, {"state": resp.content, "writer": "setup"})
    return _build_graph(store)


def run() -> ComparisonResult:
    result = run_comparison(
        build_graph_fn=_build_graph_with_setup,
        initial_state={"log": []},
        content_tokens=RESPONSE_TOKENS,
        label="4-agent high-churn (write-heavy)",
    )
    print_comparison(result)
    path = save_results(result)
    print(f"  Results saved to: {path}")
    print()
    return result


if __name__ == "__main__":
    run()
