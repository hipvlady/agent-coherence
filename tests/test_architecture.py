# Copyright (c) 2026 Arbiter contributors.
# The Coherence Protocol for AI Agents

"""Tests for architecture boundary and cycle checks."""

from __future__ import annotations

from pathlib import Path

from ccs.hardening.architecture import find_boundary_violations, find_cycles, run_architecture_checks


def test_project_architecture_has_no_boundary_or_cycle_violations() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src"
    report = run_architecture_checks(src_root)

    assert report.boundary_violations == []
    assert report.cycles == []


def test_cycle_detection_finds_strongly_connected_component() -> None:
    graph = {
        "ccs.core.a": {"ccs.core.b"},
        "ccs.core.b": {"ccs.core.c"},
        "ccs.core.c": {"ccs.core.a"},
        "ccs.core.d": set(),
    }
    cycles = find_cycles(graph)
    assert cycles == [["ccs.core.a", "ccs.core.b", "ccs.core.c"]]


def test_boundary_violation_detection_reports_forbidden_edge() -> None:
    graph = {
        "ccs.core.types": {"ccs.simulation.engine"},
        "ccs.simulation.engine": set(),
    }
    violations = find_boundary_violations(graph)
    assert len(violations) == 1
    assert "ccs.core.types" in violations[0]
    assert "ccs.simulation.engine" in violations[0]
