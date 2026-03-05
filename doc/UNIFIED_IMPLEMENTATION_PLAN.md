# CCS — Code Implementation Plan v2
## agent-coherence (repo-validated correction plan)

Validated against: `https://github.com/hipvlady/arbiter` (`dev` branch, 2026-03-05)
Current baseline: 104 tests passing, Python 3.11, CLI entry points `ccs-simulate`, `ccs-compare`, `ccs-check-architecture`.

---

## 1. Objective

Close the remaining paper-readiness and reproducibility gaps with implementation tasks C1-C9.

This v2 plan supersedes the prior v1 draft and applies the structural corrections discovered during repository validation.

---

## 2. Repository Reality (validated)

```text
arbiter/
  .github/workflows/ci.yml
  benchmarks/
    scenarios/                     # existing scenario YAMLs (7)
    results/step5/                 # existing committed baseline
  examples/multi_agent_planning.py
  src/ccs/
    adapters/
    agent/
    artifacts/
    bus/
    cli/
    coordinator/
    core/
    hardening/
    output/
    simulation/
    strategies/
    transport/
  tests/                           # 104 tests
  tools/
    benchmark_regression_smoke.py
    check_architecture.py
    run_step5_benchmarks.py
  pyproject.toml
```

---

## 3. Status Legend

- 🔴 BLOCKER: required before arXiv submission
- 🟡 IMPORTANT: required before community/venue track
- 🟢 NICE TO HAVE

---

## 4. Corrected Task Summary

| ID | Task | Priority | Effort | v1 Status |
|---|---|---|---|---|
| C1 | Create `reproduce.sh` | 🔴 | ~1h | corrected (v1 used invalid module/flags) |
| C2 | Write `REPRODUCE.md` | 🔴 | ~30m | corrected (v1 paths wrong) |
| C3 | Verify/freeze baseline in `benchmarks/results/step5/` | 🟡 | ~20m | corrected (v1 used wrong directory) |
| C4 | Add `tools/run_step_scaling.py` | 🟡 | ~45m | corrected (v1 sweep mechanism invalid) |
| C5 | Add `tools/run_artifact_scaling.py` | 🟡 | ~30m | corrected (v1 sweep mechanism invalid) |
| C6 | Add paper-aligned scenario YAML (`planning_canonical.yaml`) | 🟡 | ~30m | corrected (v1 schema invalid) |
| C7 | Add `src/ccs/core/granularity.py` | 🟡 | ~30m | valid in v1 |
| C8 | Rename `crr` -> `sync_broadcast_ratio` | 🟡 | ~20m | corrected (v1 targeted wrong files) |
| C9 | Final metadata/docs polish (`pyproject` + `README`) | 🟡 | ~30m | partial in v1 |

Recommended execution order:
`C6 -> C4 -> C5 -> C3 -> C1 -> C2 -> C7 -> C8 -> C9`

---

## 5. Detailed Work Items

### C1 — Create `reproduce.sh` (🔴)

Correction from v1:
- Do **not** call `python -m benchmarks.simulate` (not a package).
- Do **not** use non-existent CLI flags like `--sweep`.

Implementation:
- Add root `reproduce.sh` as an orchestration wrapper.
- Call:
  - `python tools/run_step5_benchmarks.py`
  - `python tools/run_step_scaling.py --output benchmarks/results/step_scaling.json`
  - `python tools/run_artifact_scaling.py --output benchmarks/results/artifact_scaling.json`
  - `python tools/verify_baseline.py --baseline benchmarks/results/step5/SUMMARY.md --tolerance 0.005`

Also add `tools/verify_baseline.py` to parse and validate baseline summary values.

Acceptance:
- `bash reproduce.sh` exits 0 in clean Python 3.11 environment.
- Outputs are created under `benchmarks/results/`.

Status:
- Completed on 2026-03-05.

### C2 — Write `REPRODUCE.md` (🔴)

Correction from v1:
- Use real paths under `benchmarks/results/step5/`.
- Do not reference nonexistent `results/scenario_a.json` or `results/baseline/`.

Implementation:
- Add root `REPRODUCE.md` with requirements, quick start, output mapping, baseline policy, and simulation scope/limitations.

Acceptance:
- Paths in table resolve to existing (or generated-by-plan) artifacts.

Status:
- Completed on 2026-03-05.

### C3 — Verify/freeze Step5 baseline (🟡)

Correction from v1:
- Baseline directory is already `benchmarks/results/step5/`.

Implementation:
- Cross-check `SUMMARY.md` values against paper tables/claims.
- If matched: record confirmation and add checksum to `manifest.json`.
- If mismatched: reconcile scenario params vs paper values before submission.

Acceptance:
- `SUMMARY.md` claims are explicitly reconciled with paper §8 values.

Status:
- Completed on 2026-03-05.

### C4 — Add `tools/run_step_scaling.py` (🟡)

Correction from v1:
- Implement as standalone `tools/` script (not CLI `--sweep`).

Implementation:
- Sweep `simulation.duration_ticks` over `[5, 10, 20, 40, 50, 100]`.
- Use `run_strategy_comparison` with `eager` and `lazy`.
- Emit `benchmarks/results/step_scaling.json` with rows:
  - `S`
  - `eager_sync_tokens_mean`
  - `lazy_sync_tokens_mean`
  - `lazy_savings_vs_eager`

Acceptance:
- `eager_sync_tokens_mean` shows approx linear growth with `S`.
- `lazy_sync_tokens_mean` grows slower under low volatility.

Status:
- Completed on 2026-03-05.
- Observation: in current simulator parameterization, lazy does not remain flatter than eager across larger `S`.

### C5 — Add `tools/run_artifact_scaling.py` (🟡)

Correction from v1:
- Implement as standalone `tools/` script (not CLI `--sweep`).

Implementation:
- Sweep `artifacts[].size_tokens` over `[4096, 8192, 32768, 65536]`.
- Use `run_strategy_comparison` with `eager` and `lazy`.
- Emit `benchmarks/results/artifact_scaling.json` with rows:
  - `artifact_tokens`
  - `eager_sync_tokens_mean`
  - `lazy_sync_tokens_mean`
  - `lazy_savings_vs_eager`
  - `absolute_savings_M`

Acceptance:
- Savings ratio is roughly size-invariant.
- Absolute savings scale with artifact size.

Status:
- Completed on 2026-03-05.
- Observation: savings ratio remains near 0.0 across artifact sizes in current parameterization.

### C6 — Add paper-aligned scenario YAML (🟡)

Correction from v1:
- Use actual schema from `src/ccs/simulation/scenarios.py`.
- Add only missing canonical scenario; avoid duplicate A/B/C/D files.

Implementation:
- Add `benchmarks/scenarios/planning_canonical.yaml` with:
  - `n=4`, `S=40`, `|d|=4096`, `V=0.05`, low `write_probability`, `conditional_injection` semantics.

Acceptance:
- `load_scenario("benchmarks/scenarios/planning_canonical.yaml")` succeeds.

Status:
- Completed on 2026-03-05.

### C7 — Add `src/ccs/core/granularity.py` (🟡)

Status:
- v1 approach is valid; file is missing and should be added.

Implementation:
- Add granularity enum/spec module.
- Export symbols via `src/ccs/core/__init__.py`.
- Add `tests/test_granularity.py` for coarse-only v0.1 assumptions.

Acceptance:
- New tests pass and constants align with v0.1 assumptions.

Status:
- Completed on 2026-03-05.

### C8 — Rename `crr` -> `sync_broadcast_ratio` (🟡)

Correction from v1:
- Edit `src/ccs/simulation/metrics.py` and `src/ccs/simulation/aggregation.py`.
- `benchmarks/metrics.py` does not exist.

Implementation:
- Rename metric property and aggregation fields.
- Update `to_dict()` key to `sync_broadcast_ratio`.
- Update all downstream references (including report template/tests/tools).

Acceptance:
- `rg -n '\\.crr\\b|"crr"|crr_mean|crr_std' src tests tools` has no stale metric-name hits.
- Full test suite remains green.

Status:
- Completed on 2026-03-05.

### C9 — Complete metadata/docs polish (🟡)

Correction from v1:
- `pyproject.toml` already exists; apply additive updates only.

Implementation:
- Add/create `README.md`.
- Ensure `pyproject.toml` has `readme`, keywords, classifiers, URLs.
- Keep license metadata aligned with repository license (`Apache-2.0`, not MIT).

Acceptance:
- Packaging metadata is internally consistent.
- `README.md` includes install, quick start, reproduce, paper, license sections.

Status:
- Completed on 2026-03-05.

---

## 6. Dependency Graph

```text
C6 -> (C4, C5) -> C1 -> C2
C3 ----------^      
C7, C8, C9 are mostly independent (C8 requires broad reference updates).
```

Execution sequence: `C6 -> C4 -> C5 -> C3 -> C1 -> C2 -> C7 -> C8 -> C9`

---

## 7. Validation Commands

```bash
python tools/check_architecture.py
pytest -q
python tools/benchmark_regression_smoke.py
python tools/run_step5_benchmarks.py
python tools/run_step_scaling.py --output benchmarks/results/step_scaling.json
python tools/run_artifact_scaling.py --output benchmarks/results/artifact_scaling.json
bash reproduce.sh
```

---

## 8. Completion Definition for v2 Plan

Plan v2 is complete when:

1. C1-C9 are implemented and merged.
2. Reproduction workflow runs end-to-end from a clean environment.
3. Step5 baseline and paper values are reconciled and documented.
4. Metric naming collision (`crr`) is resolved in code and outputs.
5. CI remains green after all changes.

Current execution status (2026-03-05):
- C1-C9 completed.
