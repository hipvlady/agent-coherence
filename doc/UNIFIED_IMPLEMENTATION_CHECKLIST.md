# Unified Implementation Checklist
## Benchmark validation fix tracker (F1-F6)

Source plan: `/Users/vladparakhin/projects/arbiter/doc/UNIFIED_IMPLEMENTATION_PLAN.md`
Last updated: 2026-03-05

Execution order:
`F1 -> F2 -> F3 -> F4 -> F5 -> F6`

---

## F1 — Broadcast Strategy (🔴)
- [x] Add `src/ccs/strategies/broadcast.py`
- [x] Add `broadcasts_every_tick()` to strategy base contract
- [x] Wire `broadcast` in selector and strategy exports
- [x] Add engine per-tick all-to-all broadcast hook
- [x] Add/extend tests for broadcast behavior + token baseline

## F2 — Canonical Scenarios (🔴)
- [x] Update `benchmarks/scenarios/planning_canonical.yaml` to 3 artifacts
- [x] Add `analysis_canonical.yaml`
- [x] Add `dev_canonical.yaml`
- [x] Add `churn_canonical.yaml`
- [x] Validate all four scenarios load successfully

## F3 — Canonical Runner (🔴)
- [x] Add `tools/run_canonical_benchmarks.py`
- [x] Emit per-scenario JSON + HTML to `benchmarks/results/canonical/`
- [x] Emit `SUMMARY.md` + `manifest.json` with checksum
- [ ] Assert scenarios match Table 1 tolerances

## F4 — Step Scaling Broadcast Baseline (🔴)
- [x] Include `broadcast` strategy in `tools/run_step_scaling.py`
- [x] Add `broadcast_sync_tokens_mean` output field
- [x] Compute `lazy_savings_vs_broadcast`
- [x] Keep `lazy_savings_vs_eager` as reference

## F5 — Artifact Scaling Broadcast Baseline (🔴)
- [x] Include `broadcast` strategy in `tools/run_artifact_scaling.py`
- [x] Add `broadcast_sync_tokens_mean` output field
- [x] Compute `lazy_savings_vs_broadcast`
- [x] Keep `lazy_savings_vs_eager` as reference

## F6 — Step5 Runner Canonical Integration (🟡)
- [x] Include `planning_canonical.yaml` in `tools/run_step5_benchmarks.py`
- [x] Include `broadcast` strategy in step5 run
- [x] Update step5 summary columns/savings baseline



---

## Validation
- [x] `pytest -q`
- [x] `pytest tests/test_strategies.py -k broadcast -v`
- [ ] `python tools/run_canonical_benchmarks.py`
- [x] `python tools/run_step_scaling.py`
- [x] `python tools/run_artifact_scaling.py`
- [x] `python tools/run_step5_benchmarks.py`

Validation note:
- `tools/run_canonical_benchmarks.py` currently exits non-zero because observed savings are higher than configured Table 1 targets.
- Latest rerun (2026-03-05): `pytest=0`, `broadcast-tests=0`, `canonical=1`, `step-scaling=0`, `artifact-scaling=0`, `step5=0`.
