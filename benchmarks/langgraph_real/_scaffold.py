"""Shared scaffold for real-LangGraph benchmarks.

Provides helpers for:
- Building a FakeChatModel with realistic response sizes
- Running the same graph with InMemoryStore vs CCSStore and comparing results
- Printing a structured comparison table
- Saving results to benchmarks/results/langgraph_real/
"""

from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from ccs.adapters.ccsstore import CCSStore, StoreMetricEvent

_RESULTS_DIR = Path(__file__).parent.parent / "results" / "langgraph_real"


# ---------------------------------------------------------------------------
# FakeChatModel factory
# ---------------------------------------------------------------------------

def make_fake_llm(response_tokens: int = 320) -> GenericFakeChatModel:
    """Return a FakeChatModel that yields a fixed-size response on every invoke.

    The content is a repeated word string sized so that _estimate_tokens()
    (len // 4) approximates response_tokens.
    """
    content = ("word " * (response_tokens * 4 // 5)).strip()
    # Cycle so the model can be called any number of times reproducibly.
    messages = itertools.cycle([AIMessage(content=content)])
    return GenericFakeChatModel(messages=messages)


# ---------------------------------------------------------------------------
# Comparison result
# ---------------------------------------------------------------------------

@dataclass
class ComparisonResult:
    label: str
    baseline_tokens: int
    ccs_tokens: int
    num_ops: int
    num_hits: int
    num_misses: int
    num_writes: int
    content_tokens: int
    elapsed_s: float

    @property
    def cache_hit_rate(self) -> float:
        reads = self.num_hits + self.num_misses
        return self.num_hits / reads if reads > 0 else 0.0

    @property
    def token_reduction_pct(self) -> float:
        if self.baseline_tokens == 0:
            return 0.0
        return (self.baseline_tokens - self.ccs_tokens) / self.baseline_tokens * 100


# ---------------------------------------------------------------------------
# run_comparison
# ---------------------------------------------------------------------------

def run_comparison(
    build_graph_fn: Callable[[Any], Any],
    initial_state: dict,
    content_tokens: int,
    label: str = "Benchmark",
) -> ComparisonResult:
    """Run the graph with CCSStore and compute a no-cache baseline from op counts.

    The baseline is calculated as num_ops × content_tokens — equivalent to what
    InMemoryStore would cost if every operation paid the full content transfer cost.
    (InMemoryStore does not support CCSStore's cross-agent namespace sharing, so
    running the same graph with InMemoryStore would fail for reads by non-writer agents.)

    Args:
        build_graph_fn: Callable(store) → compiled StateGraph.
        initial_state: Initial state dict passed to graph.invoke().
        content_tokens: Expected token size of each artifact (used for baseline calc).
        label: Human-readable benchmark name.

    Returns:
        ComparisonResult with token accounting for both the baseline and CCS runs.
    """
    events: list[StoreMetricEvent] = []
    ccs_store = CCSStore(strategy="lazy", on_metric=events.append)

    t0 = time.perf_counter()
    ccs_graph = build_graph_fn(ccs_store)
    ccs_graph.invoke(initial_state)
    elapsed = time.perf_counter() - t0

    put_events = [e for e in events if e.operation == "put"]
    get_events = [e for e in events if e.operation == "get"]
    hits = [e for e in get_events if e.cache_hit]
    misses = [e for e in get_events if not e.cache_hit]

    num_ops = len(put_events) + len(get_events)
    # Baseline: every op pays full content cost (no-cache semantics)
    baseline_tokens = num_ops * content_tokens
    ccs_tokens = sum(e.tokens_consumed for e in events if e.operation in ("put", "get"))

    return ComparisonResult(
        label=label,
        baseline_tokens=baseline_tokens,
        ccs_tokens=ccs_tokens,
        num_ops=num_ops,
        num_hits=len(hits),
        num_misses=len(misses),
        num_writes=len(put_events),
        content_tokens=content_tokens,
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# print_comparison
# ---------------------------------------------------------------------------

def print_comparison(result: ComparisonResult) -> None:
    """Print a structured comparison table matching the langgraph_planner format."""
    reads = result.num_hits + result.num_misses
    print()
    print(f"Benchmark: {result.label}")
    print(f"Content: ~{result.content_tokens} tokens per artifact")
    print()
    print(
        f"  InMemoryStore:  {result.baseline_tokens:>6} tokens"
        f"   ({result.num_ops} ops × {result.content_tokens})"
    )
    print(
        f"  CCSStore lazy:  {result.ccs_tokens:>6} tokens"
        f"   ({result.num_writes} write + {result.num_misses} misses) × {result.content_tokens}"
        f" + {result.num_hits} hits × 1"
    )
    print()
    print(
        f"  Cache hit rate:   {result.num_hits} / {reads} = {result.cache_hit_rate:.0%}"
        f"    ← fraction of reads served from cache"
    )
    print(
        f"  Token reduction:  {result.token_reduction_pct:.0f}%"
        f"            ← actual savings vs no-cache baseline"
    )
    print(f"  Elapsed (CCS):    {result.elapsed_s:.3f}s")
    print()


# ---------------------------------------------------------------------------
# save_results
# ---------------------------------------------------------------------------

def save_results(result: ComparisonResult, filename: str | None = None) -> Path:
    """Write the comparison result as JSON to benchmarks/results/langgraph_real/.

    Returns the path of the written file.
    """
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    reads = result.num_hits + result.num_misses
    payload = {
        "label": result.label,
        "baseline_tokens": result.baseline_tokens,
        "ccs_tokens": result.ccs_tokens,
        "cache_hit_rate": round(result.cache_hit_rate, 4),
        "token_reduction_pct": round(result.token_reduction_pct, 2),
        "num_ops": result.num_ops,
        "num_writes": result.num_writes,
        "num_reads": reads,
        "num_hits": result.num_hits,
        "num_misses": result.num_misses,
        "content_tokens": result.content_tokens,
        "elapsed_s": round(result.elapsed_s, 4),
    }
    safe_label = result.label.lower().replace(" ", "_").replace("/", "_")
    fname = filename or f"{safe_label}.json"
    path = _RESULTS_DIR / fname
    path.write_text(json.dumps(payload, indent=2))
    return path
