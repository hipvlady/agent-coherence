"""Tests for benchmark harness Stage 1 (R4-R6).

Covers tools/run_benchmarks.py, tools/benchmark_drift_check.py,
and tools/check_readme_numbers.py without running the actual LangGraph workloads.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent

# run_benchmarks.py imports from benchmarks.langgraph_real, which is a namespace package
# rooted at the repo root — not discovered via the "src" pythonpath in pyproject.toml.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _make_result(label: str, baseline: int, ccs: int) -> object:
    """Return a duck-typed ComparisonResult-like object for testing.

    Uses MagicMock to avoid importing benchmarks.langgraph_real._scaffold, which
    requires the repo root on sys.path (not guaranteed in isolated test environments).
    """
    result = MagicMock()
    result.label = label
    result.baseline_tokens = baseline
    result.ccs_tokens = ccs
    result.token_reduction_pct = (baseline - ccs) / baseline * 100
    return result


_FAKE_RESULTS = [
    _make_result("4-agent planning pipeline (read-heavy)", 4160, 1301),
    _make_result("3-agent code review (write-moderate)", 5320, 2835),
    _make_result("4-agent high-churn (write-heavy)", 3250, 2317),
]

# Expected token_reduction_pct values derived from _FAKE_RESULTS
_FAKE_PCTS = [round(r.token_reduction_pct, 2) for r in _FAKE_RESULTS]


# ---------------------------------------------------------------------------
# Unit 1: run_benchmarks
# ---------------------------------------------------------------------------


def _import_run_benchmarks():
    """Import tools/run_benchmarks.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "run_benchmarks", _REPO_ROOT / "tools" / "run_benchmarks.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def patched_benchmarks(monkeypatch):
    """Patch the three bench modules so run() returns _FAKE_RESULTS without LangGraph."""
    mod = _import_run_benchmarks()

    for i, bench_mod in enumerate(mod._BENCHMARKS):
        result = _FAKE_RESULTS[i]
        monkeypatch.setattr(bench_mod, "run", lambda r=result: r)

    return mod


def test_latest_json_written(patched_benchmarks, tmp_path):
    mod = patched_benchmarks
    latest_path = tmp_path / "latest.json"
    expected_path = tmp_path / "expected.json"

    with patch.object(mod, "_LATEST_PATH", latest_path), patch.object(
        mod, "_EXPECTED_PATH", expected_path
    ), patch.object(mod, "_RESULTS_DIR", tmp_path):
        mod.main()

    assert latest_path.exists()
    data = json.loads(latest_path.read_text())
    assert "generated_at" in data
    workloads = data["workloads"]
    assert len(workloads) == 3
    for w in workloads:
        assert set(w.keys()) == {"name", "baseline_tokens", "ccs_tokens", "token_reduction_pct"}


def test_latest_json_workload_names(patched_benchmarks, tmp_path):
    mod = patched_benchmarks
    latest_path = tmp_path / "latest.json"
    expected_path = tmp_path / "expected.json"

    with patch.object(mod, "_LATEST_PATH", latest_path), patch.object(
        mod, "_EXPECTED_PATH", expected_path
    ), patch.object(mod, "_RESULTS_DIR", tmp_path):
        mod.main()

    workloads = json.loads(latest_path.read_text())["workloads"]
    names = {w["name"] for w in workloads}
    assert "4-agent planning pipeline (read-heavy)" in names
    assert "3-agent code review (write-moderate)" in names
    assert "4-agent high-churn (write-heavy)" in names


def test_bootstrap_creates_expected_json(patched_benchmarks, tmp_path):
    mod = patched_benchmarks
    latest_path = tmp_path / "latest.json"
    expected_path = tmp_path / "expected.json"

    assert not expected_path.exists()

    with patch.object(mod, "_LATEST_PATH", latest_path), patch.object(
        mod, "_EXPECTED_PATH", expected_path
    ), patch.object(mod, "_RESULTS_DIR", tmp_path):
        mod.main()

    assert expected_path.exists()
    data = json.loads(expected_path.read_text())
    assert "workloads" in data
    assert "generated_at" not in data  # expected.json has no timestamp
    assert len(data["workloads"]) == 3


def test_bootstrap_does_not_overwrite_existing_expected(patched_benchmarks, tmp_path):
    mod = patched_benchmarks
    latest_path = tmp_path / "latest.json"
    expected_path = tmp_path / "expected.json"

    # Pre-seed expected.json with sentinel value
    sentinel = {"workloads": [{"name": "sentinel", "baseline_tokens": 1, "ccs_tokens": 1, "token_reduction_pct": 0.0}]}
    expected_path.write_text(json.dumps(sentinel))

    with patch.object(mod, "_LATEST_PATH", latest_path), patch.object(
        mod, "_EXPECTED_PATH", expected_path
    ), patch.object(mod, "_RESULTS_DIR", tmp_path):
        mod.main()

    # expected.json must not have been overwritten
    assert json.loads(expected_path.read_text()) == sentinel


def test_bootstrap_message_printed_on_first_run(patched_benchmarks, tmp_path, capsys):
    mod = patched_benchmarks
    latest_path = tmp_path / "latest.json"
    expected_path = tmp_path / "expected.json"

    with patch.object(mod, "_LATEST_PATH", latest_path), patch.object(
        mod, "_EXPECTED_PATH", expected_path
    ), patch.object(mod, "_RESULTS_DIR", tmp_path):
        mod.main()

    out = capsys.readouterr().out
    assert "Bootstrapped benchmarks/expected.json" in out


def test_no_bootstrap_message_on_subsequent_run(patched_benchmarks, tmp_path, capsys):
    mod = patched_benchmarks
    latest_path = tmp_path / "latest.json"
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps({"workloads": []}))

    with patch.object(mod, "_LATEST_PATH", latest_path), patch.object(
        mod, "_EXPECTED_PATH", expected_path
    ), patch.object(mod, "_RESULTS_DIR", tmp_path):
        mod.main()

    out = capsys.readouterr().out
    assert "Bootstrapped" not in out


# ---------------------------------------------------------------------------
# Unit 3: benchmark_drift_check
# ---------------------------------------------------------------------------


def _import_drift_check():
    spec = importlib.util.spec_from_file_location(
        "benchmark_drift_check", _REPO_ROOT / "tools" / "benchmark_drift_check.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _workload_entry(name: str, pct: float) -> dict:
    return {"name": name, "baseline_tokens": 1000, "ccs_tokens": 500, "token_reduction_pct": pct}


@pytest.fixture()
def drift_check():
    return _import_drift_check()


def test_drift_check_passes_within_threshold(drift_check, tmp_path):
    latest = tmp_path / "latest.json"
    expected = tmp_path / "expected.json"
    _write_json(latest, {"workloads": [_workload_entry("workload_a", 68.73)]})
    _write_json(expected, {"workloads": [_workload_entry("workload_a", 68.73)]})

    assert drift_check.check_drift(latest, expected) is True


def test_drift_check_passes_at_exactly_threshold(drift_check, tmp_path):
    # delta == 1.0 should pass (strict >)
    latest = tmp_path / "latest.json"
    expected = tmp_path / "expected.json"
    _write_json(latest, {"workloads": [_workload_entry("workload_a", 69.73)]})
    _write_json(expected, {"workloads": [_workload_entry("workload_a", 68.73)]})

    assert drift_check.check_drift(latest, expected) is True


def test_drift_check_fails_above_threshold(drift_check, tmp_path):
    latest = tmp_path / "latest.json"
    expected = tmp_path / "expected.json"
    _write_json(latest, {"workloads": [_workload_entry("workload_a", 70.74)]})
    _write_json(expected, {"workloads": [_workload_entry("workload_a", 68.73)]})

    assert drift_check.check_drift(latest, expected) is False


def test_drift_check_fails_multiple_drifted(drift_check, tmp_path):
    latest = tmp_path / "latest.json"
    expected = tmp_path / "expected.json"
    _write_json(latest, {"workloads": [
        _workload_entry("a", 72.0),
        _workload_entry("b", 50.0),
        _workload_entry("c", 32.0),
    ]})
    _write_json(expected, {"workloads": [
        _workload_entry("a", 68.73),
        _workload_entry("b", 46.71),
        _workload_entry("c", 28.71),
    ]})

    assert drift_check.check_drift(latest, expected) is False


def test_drift_check_fails_on_missing_expected(drift_check, tmp_path):
    latest = tmp_path / "latest.json"
    _write_json(latest, {"workloads": [_workload_entry("a", 68.0)]})
    expected = tmp_path / "nonexistent.json"

    assert drift_check.check_drift(latest, expected) is False


def test_drift_check_fails_on_missing_latest(drift_check, tmp_path):
    expected = tmp_path / "expected.json"
    _write_json(expected, {"workloads": [_workload_entry("a", 68.0)]})
    latest = tmp_path / "nonexistent.json"

    assert drift_check.check_drift(latest, expected) is False


def test_drift_check_fails_workload_in_expected_not_in_latest(drift_check, tmp_path):
    # Workload present in expected but absent from latest
    latest = tmp_path / "latest.json"
    expected = tmp_path / "expected.json"
    _write_json(latest, {"workloads": [_workload_entry("workload_a", 68.73)]})
    _write_json(expected, {"workloads": [
        _workload_entry("workload_a", 68.73),
        _workload_entry("workload_b_missing", 46.71),
    ]})

    assert drift_check.check_drift(latest, expected) is False


def test_drift_check_fails_workload_in_latest_not_in_expected(drift_check, tmp_path):
    # Workload present in latest but absent from expected (unknown workload)
    latest = tmp_path / "latest.json"
    expected = tmp_path / "expected.json"
    _write_json(latest, {"workloads": [
        _workload_entry("workload_a", 68.73),
        _workload_entry("new_unknown_workload", 55.0),
    ]})
    _write_json(expected, {"workloads": [_workload_entry("workload_a", 68.73)]})

    assert drift_check.check_drift(latest, expected) is False


# ---------------------------------------------------------------------------
# Unit 5: check_readme_numbers
# ---------------------------------------------------------------------------


def _import_readme_check():
    spec = importlib.util.spec_from_file_location(
        "check_readme_numbers", _REPO_ROOT / "tools" / "check_readme_numbers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def readme_check():
    return _import_readme_check()


def _make_expected_json(path: Path, pctnums: list[float]) -> None:
    workloads = [
        {"name": f"workload_{i}", "baseline_tokens": 1000, "ccs_tokens": 500, "token_reduction_pct": p}
        for i, p in enumerate(pctnums)
    ]
    path.write_text(json.dumps({"workloads": workloads}))


def _make_readme(path: Path, savings_vals: list[int]) -> None:
    rows = "\n".join(f"| Workload {i} | 4 | 12:1 | 75% | 4160 | 1301 | **{v}%** |" for i, v in enumerate(savings_vals))
    path.write_text(f"## Real-workload benchmarks\n\n| Workload | Agents | Reads:Writes | Hit rate | Baseline tokens | CCSStore tokens | Savings |\n|---|---|---|---|---|---|---|\n{rows}\n\n## Next section\n")


def test_readme_check_passes_matching_values(readme_check, tmp_path):
    expected = tmp_path / "expected.json"
    readme = tmp_path / "README.md"
    _make_expected_json(expected, [68.73, 46.71, 28.71])
    _make_readme(readme, [69, 47, 29])

    assert readme_check.check_readme_numbers(expected, readme) is True


def test_readme_check_fails_stale_value(readme_check, tmp_path):
    expected = tmp_path / "expected.json"
    readme = tmp_path / "README.md"
    _make_expected_json(expected, [70.1, 46.71, 28.71])  # display_pct = 70
    _make_readme(readme, [69, 47, 29])  # README still says 69

    assert readme_check.check_readme_numbers(expected, readme) is False


def test_readme_check_fails_missing_expected(readme_check, tmp_path):
    readme = tmp_path / "README.md"
    _make_readme(readme, [69, 47, 29])
    expected = tmp_path / "nonexistent.json"

    assert readme_check.check_readme_numbers(expected, readme) is False


def test_readme_check_round_trip(readme_check, tmp_path):
    # 68.73 → 69, 46.71 → 47, 28.71 → 29
    expected = tmp_path / "expected.json"
    readme = tmp_path / "README.md"
    _make_expected_json(expected, [68.73, 46.71, 28.71])
    _make_readme(readme, [69, 47, 29])

    assert readme_check.check_readme_numbers(expected, readme) is True


def test_readme_check_section_not_found(readme_check, tmp_path):
    expected = tmp_path / "expected.json"
    readme = tmp_path / "README.md"
    _make_expected_json(expected, [68.73])
    readme.write_text("## Some other section\n\n**69%**\n")  # right value, wrong section

    assert readme_check.check_readme_numbers(expected, readme) is False


def test_readme_check_values_outside_section_ignored(readme_check, tmp_path):
    # **69%** appears BEFORE the benchmark section — should not count
    expected = tmp_path / "expected.json"
    readme = tmp_path / "README.md"
    _make_expected_json(expected, [68.73])
    readme.write_text(
        "## Introduction\n**69%** savings mentioned here\n\n"
        "## Real-workload benchmarks\n| Workload | Savings |\n|---|---|\n| W | **55%** |\n\n## Next\n"
    )

    assert readme_check.check_readme_numbers(expected, readme) is False
