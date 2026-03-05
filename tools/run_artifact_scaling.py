# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Artifact-size sweep: test eager vs lazy savings across artifact token sizes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ccs.simulation.engine import run_strategy_comparison
from ccs.simulation.scenarios import load_scenario

ARTIFACT_SIZES = [4096, 8192, 32768, 65536]
RUNS_PER_POINT = 10
STRATEGIES = ["eager", "lazy"]
SEED_START = 20260305


def _make_scenario(artifact_tokens: int) -> dict:
    scenario = load_scenario(str(REPO_ROOT / "benchmarks" / "scenarios" / "planning_canonical.yaml"))
    scenario["simulation"]["seed"] = SEED_START
    scenario["scenario"]["name"] = f"artifact-scaling-{artifact_tokens}t"
    scenario["artifacts"][0]["size_tokens"] = artifact_tokens
    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Artifact-size scaling sweep for CCS benchmarks.")
    parser.add_argument("--output", default="benchmarks/results/artifact_scaling.json")
    args = parser.parse_args(argv)

    rows: list[dict[str, float | int]] = []
    for artifact_tokens in ARTIFACT_SIZES:
        scenario = _make_scenario(artifact_tokens)
        report = run_strategy_comparison(
            scenario,
            strategies=STRATEGIES,
            runs=RUNS_PER_POINT,
            seed_start=SEED_START,
        )
        aggregated = {item["strategy"]: item for item in report.aggregated}
        eager_sync = float(aggregated["eager"]["synchronization_tokens_mean"])
        lazy_sync = float(aggregated["lazy"]["synchronization_tokens_mean"])
        savings = 0.0 if eager_sync == 0 else max(0.0, 1.0 - lazy_sync / eager_sync)
        rows.append(
            {
                "artifact_tokens": artifact_tokens,
                "eager_sync_tokens_mean": eager_sync,
                "lazy_sync_tokens_mean": lazy_sync,
                "lazy_savings_vs_eager": round(savings, 4),
                "absolute_savings_M": round((eager_sync - lazy_sync) / 1_000_000, 3),
            }
        )
        print(
            f"  |d|={artifact_tokens:>6}: eager={eager_sync:>12.1f} "
            f"lazy={lazy_sync:>12.1f} savings={savings:.1%} "
            f"absolute={rows[-1]['absolute_savings_M']:.3f}M"
        )

    payload = {
        "sweep": "artifact_size",
        "runs_per_point": RUNS_PER_POINT,
        "strategies": STRATEGIES,
        "rows": rows,
    }
    output_path = REPO_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
