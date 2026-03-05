# CCS — Benchmark Validation Fix Plan
## agent-coherence (F1-F6 execution)

Derived from: `benchmark_validation_report.docx` (2026-03-05)
Validated against: `hipvlady/arbiter` (`dev`, 2026-03-05)

---

## 1. Objective

Close benchmark-baseline gaps by executing F1-F6 in strict order and validating outputs.

Execution order:
`F1 -> F2 -> F3 -> F4 -> F5 -> F6`

---

## 2. Status Legend

- 🔴 BLOCKER: required before arXiv submission
- 🟡 IMPORTANT: required before venue track

---

## 3. Task Summary

| ID | Task | Type | Priority | Effort | Status |
|---|---|---|---|---|---|
| F1 | Add `BroadcastStrategy` to `src/ccs/strategies/` | Code | 🔴 | ~1h | Completed (2026-03-05) |
| F2 | Add canonical scenario YAMLs (A/B/C/D) | YAML | 🔴 | ~30m | Completed (2026-03-05) |
| F3 | Add `tools/run_canonical_benchmarks.py` | Code | 🔴 | ~1h | Implemented; target mismatch |
| F4 | Fix `tools/run_step_scaling.py` with broadcast baseline | Code | 🔴 | ~30m | Completed (2026-03-05) |
| F5 | Fix `tools/run_artifact_scaling.py` with broadcast baseline | Code | 🔴 | ~20m | Completed (2026-03-05) |
| F6 | Add `planning_canonical` to `run_step5_benchmarks.py` (+ broadcast column) | Code | 🟡 | ~15m | Completed (2026-03-05) |

---

## 4. Detailed Status

### F1 — Broadcast Strategy (🔴)
Status:
- Completed on 2026-03-05.
- Validation: `pytest tests/test_strategies.py -k broadcast -v` passed (3 tests).

### F2 — Canonical Scenario Suite (🔴)
Status:
- Completed on 2026-03-05.
- Validation: all four canonical scenarios load via `load_scenario(...)`.

### F3 — Canonical Benchmark Runner (🔴)
Status:
- Implemented on 2026-03-05.
- Current result: script runs and writes outputs, but tolerance gate fails (`all_pass = false`) because simulated savings exceed report targets.

### F4 — Step Scaling Baseline Fix (🔴)
Status:
- Completed on 2026-03-05.
- Observation: `lazy_savings_vs_broadcast` rises with `S`, but around 95% at `S=40` (higher than 85% target in report plan).

### F5 — Artifact Scaling Baseline Fix (🔴)
Status:
- Completed on 2026-03-05.
- Observation: savings ratio is stable across sizes (~94.8%-95.0%), but materially above report targets.

### F6 — Step5 Runner Canonical Integration (🟡)
Status:
- Completed on 2026-03-05.
- Validation: regenerated step5 summary includes `planning-canonical` and `broadcast` columns/rows.

---

## 5. Validation Commands

```bash
pytest -q
pytest tests/test_strategies.py -k broadcast -v
python tools/run_canonical_benchmarks.py
python tools/run_step_scaling.py
python tools/run_artifact_scaling.py
python tools/run_step5_benchmarks.py
```

---

## 6. Current Execution Status

- F1, F2, F4, F5, F6 complete.
- F3 implemented but currently failing tolerance gate.
- Validation run (2026-03-05):
  - `pytest -q`: pass (106 tests)
  - `pytest tests/test_strategies.py -k broadcast -v`: pass (3 selected tests)
  - `python tools/run_step_scaling.py`: pass
  - `python tools/run_artifact_scaling.py`: pass
  - `python tools/run_step5_benchmarks.py`: pass
  - `python tools/run_canonical_benchmarks.py`: fail (target mismatch)
- Latest rerun summary (2026-03-05):
  - return codes: `pytest=0`, `broadcast-tests=0`, `canonical=1`, `step-scaling=0`, `artifact-scaling=0`, `step5=0`
