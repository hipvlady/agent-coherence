"""CI drift check: compare benchmarks/results/latest.json against benchmarks/expected.json.

Exits 0 if all workload token_reduction_pct values are within 1 percentage point of the
committed baseline. Exits 1 on any drift > 1.0pp, missing files, or workload set mismatch.

Usage:
    python tools/benchmark_drift_check.py
    make benchmark-check
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_LATEST_PATH = _REPO_ROOT / "benchmarks" / "results" / "latest.json"
_EXPECTED_PATH = _REPO_ROOT / "benchmarks" / "expected.json"

_THRESHOLD = 1.0  # strict >; exactly 1.0pp passes


def check_drift(latest_path: Path, expected_path: Path) -> bool:
    """Compare latest against expected; print findings; return True if check passes."""
    if not expected_path.exists():
        print(
            f"ERROR: {expected_path} not found — "
            "run `make benchmark` to establish a baseline, then commit the file.",
            file=sys.stderr,
        )
        return False

    if not latest_path.exists():
        print(
            f"ERROR: {latest_path} not found — run `make benchmark` first.",
            file=sys.stderr,
        )
        return False

    latest_data = json.loads(latest_path.read_text())
    expected_data = json.loads(expected_path.read_text())

    latest_by_name = {w["name"]: w for w in latest_data.get("workloads", [])}
    expected_by_name = {w["name"]: w for w in expected_data.get("workloads", [])}

    errors: list[str] = []

    # Workloads in expected but missing from latest
    for name in expected_by_name:
        if name not in latest_by_name:
            errors.append(f"  MISSING from latest: '{name}' (present in expected)")

    # Workloads in latest but not in expected
    for name in latest_by_name:
        if name not in expected_by_name:
            errors.append(f"  UNEXPECTED in latest: '{name}' (not in expected)")

    if errors:
        print("Workload set mismatch:", file=sys.stderr)
        for err in errors:
            print(err, file=sys.stderr)
        print(
            "\nUpdate benchmarks/expected.json by running `make benchmark` and committing the result.",
            file=sys.stderr,
        )
        return False

    # Drift check for matched workloads
    col = 42
    header = f"  {'Workload':<{col}} {'Expected':>8}  {'Actual':>8}  {'Delta':>7}"
    rows: list[tuple[str, float, float, float]] = []

    for name, expected_w in expected_by_name.items():
        latest_w = latest_by_name[name]
        delta = abs(latest_w["token_reduction_pct"] - expected_w["token_reduction_pct"])
        rows.append((name, expected_w["token_reduction_pct"], latest_w["token_reduction_pct"], delta))

    drifted = [(n, e, a, d) for n, e, a, d in rows if d > _THRESHOLD]

    print(header)
    print("-" * (col + 30))
    for name, exp, act, delta in rows:
        flag = " ← DRIFT" if delta > _THRESHOLD else ""
        print(
            f"  {name:<{col}} {exp:>7.2f}%  {act:>7.2f}%  {delta:>6.2f}pp{flag}"
        )
    print()

    if drifted:
        print(
            f"Benchmark regression check FAILED: {len(drifted)} workload(s) drifted > {_THRESHOLD}pp.",
            file=sys.stderr,
        )
        print(
            "Run `make benchmark` and commit the updated benchmarks/expected.json if the change is intentional.",
            file=sys.stderr,
        )
        return False

    print("Benchmark regression check passed.")
    return True


def main() -> None:
    passed = check_drift(_LATEST_PATH, _EXPECTED_PATH)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
