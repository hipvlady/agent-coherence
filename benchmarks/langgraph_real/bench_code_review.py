"""Real LangGraph benchmark — write-moderate code review workload.

3-agent graph: reviewer_a → reviewer_b → synthesizer.
Each agent reads the shared codebase 3× (simulating multiple analysis passes)
before writing their review. Synthesizer reads all three artifacts.

Write frequency: 4 writes / ~15 total ops → moderate.
Expected hit rate: ~55-65% (repeated reads of same artifact hit cache).

Run:
  python benchmarks/langgraph_real/bench_code_review.py
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

CODE_KEY = "codebase"
REVIEW_A_KEY = "review_a"
REVIEW_B_KEY = "review_b"
SCOPE = "shared"
RESPONSE_TOKENS = 280
CODE_READ_PASSES = 3   # multi-pass analysis per reviewer
REVIEW_READ_PASSES = 2  # synthesizer re-reads each review


class GraphState(TypedDict):
    log: list[str]


def _build_graph(store) -> "CompiledStateGraph":
    llm = make_fake_llm(response_tokens=RESPONSE_TOKENS)

    def reviewer_a_node(state: GraphState) -> dict:
        s = lg_get_store()
        for _ in range(CODE_READ_PASSES):
            item = s.get(("reviewer_a", SCOPE), CODE_KEY)
            assert item is not None
        resp = llm.invoke([HumanMessage(content="Review this code.")])
        s.put(("reviewer_a", SCOPE), REVIEW_A_KEY, {"review": resp.content})
        return {"log": [*state["log"], "reviewer_a: analysed code + wrote review"]}

    def reviewer_b_node(state: GraphState) -> dict:
        s = lg_get_store()
        for _ in range(CODE_READ_PASSES):
            item = s.get(("reviewer_b", SCOPE), CODE_KEY)
            assert item is not None
        # Also reads reviewer_a's review 2× (comparing perspectives)
        for _ in range(REVIEW_READ_PASSES):
            item = s.get(("reviewer_b", SCOPE), REVIEW_A_KEY)
            assert item is not None
        resp = llm.invoke([HumanMessage(content="Review this code.")])
        s.put(("reviewer_b", SCOPE), REVIEW_B_KEY, {"review": resp.content})
        return {"log": [*state["log"], "reviewer_b: analysed code + wrote review"]}

    def synthesizer_node(state: GraphState) -> dict:
        s = lg_get_store()
        for _ in range(CODE_READ_PASSES):
            item = s.get(("synthesizer", SCOPE), CODE_KEY)
            assert item is not None
        for _ in range(REVIEW_READ_PASSES):
            item = s.get(("synthesizer", SCOPE), REVIEW_A_KEY)
            assert item is not None
        for _ in range(REVIEW_READ_PASSES):
            item = s.get(("synthesizer", SCOPE), REVIEW_B_KEY)
            assert item is not None
        resp = llm.invoke([HumanMessage(content="Synthesize these reviews.")])
        s.put(("synthesizer", SCOPE), "final_review", {"synthesis": resp.content})
        return {"log": [*state["log"], "synthesizer: synthesised reviews"]}

    builder = StateGraph(GraphState)
    builder.add_node("reviewer_a", reviewer_a_node)
    builder.add_node("reviewer_b", reviewer_b_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_edge(START, "reviewer_a")
    builder.add_edge("reviewer_a", "reviewer_b")
    builder.add_edge("reviewer_b", "synthesizer")
    builder.add_edge("synthesizer", END)
    return builder.compile(store=store)


def _build_graph_with_codebase(store) -> "CompiledStateGraph":
    llm = make_fake_llm(response_tokens=RESPONSE_TOKENS)
    resp = llm.invoke([HumanMessage(content="Here is the source code to review.")])
    store.put(("setup", SCOPE), CODE_KEY, {"code": resp.content})
    return _build_graph(store)


def run() -> ComparisonResult:
    result = run_comparison(
        build_graph_fn=_build_graph_with_codebase,
        initial_state={"log": []},
        content_tokens=RESPONSE_TOKENS,
        label="3-agent code review (write-moderate)",
    )
    print_comparison(result)
    path = save_results(result)
    print(f"  Results saved to: {path}")
    print()
    return result


if __name__ == "__main__":
    run()
