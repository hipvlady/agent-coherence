"""Run all three LangGraph real-workload benchmarks and write consolidated results.

Writes benchmarks/results/latest.json (compact schema; gitignored).
On first run, bootstraps benchmarks/expected.json (commit to fix the baseline).

Requires: pip install -e ".[langgraph,benchmark]"
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# benchmarks/ is a namespace package at the repo root — not on sys.path when this
# script is invoked as `python tools/run_benchmarks.py` (Python adds the script's
# directory, not the repo root, to sys.path for script invocations).
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.langgraph_real import bench_code_review, bench_high_churn, bench_planner  # noqa: E402
from benchmarks.langgraph_real._scaffold import ComparisonResult  # noqa: E402
_RESULTS_DIR = _REPO_ROOT / "benchmarks" / "results"
_LATEST_PATH = _RESULTS_DIR / "latest.json"
_EXPECTED_PATH = _REPO_ROOT / "benchmarks" / "expected.json"

_BENCHMARKS = [bench_planner, bench_code_review, bench_high_churn]
_COL_WIDTH = 42


def _workload_entry(result: ComparisonResult) -> dict:
    return {
        "name": result.label,
        "baseline_tokens": result.baseline_tokens,
        "ccs_tokens": result.ccs_tokens,
        "token_reduction_pct": round(result.token_reduction_pct, 2),
    }


def _print_summary_table(workloads: list[dict]) -> None:
    width = _COL_WIDTH + 30
    print()
    print("=" * width)
    print("  Consolidated benchmark results")
    print(f"  {'Workload':<{_COL_WIDTH}} {'Baseline':>8}  {'CCS':>8}  {'Savings':>7}")
    print("-" * width)
    for w in workloads:
        print(
            f"  {w['name']:<{_COL_WIDTH}} {w['baseline_tokens']:>8}"
            f"  {w['ccs_tokens']:>8}  {w['token_reduction_pct']:>6.1f}%"
        )
    print("=" * width)
    print()


def main() -> None:
    results = [bench.run() for bench in _BENCHMARKS]
    workloads = [_workload_entry(r) for r in results]

    _print_summary_table(workloads)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _LATEST_PATH.write_text(
        json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat(), "workloads": workloads},
            indent=2,
        )
    )
    try:
        display = _LATEST_PATH.relative_to(_REPO_ROOT)
    except ValueError:
        display = _LATEST_PATH
    print(f"Results written to: {display}")

    if not _EXPECTED_PATH.exists():
        _EXPECTED_PATH.write_text(json.dumps({"workloads": workloads}, indent=2))
        print()
        print(
            "Bootstrapped benchmarks/expected.json"
            " — commit this file to fix the reference baseline."
        )

    print()


if __name__ == "__main__":
    main()
