# Canonical Benchmark Summary — Paper §8 Table 1 Reproduction

- generated_on: 2026-03-10
- baseline: T_broadcast = n*S*m*|d| = 1,966,080 tokens
- runs_per_strategy: 10
- strategies: broadcast, lazy

| Scenario | V | T_broadcast | T_lazy | Savings | Target | Status |
|---|---|---:|---:|---:|---:|---|
| A: Planning | 0.05 | 1,979,597 | 98,055 | 95.0% | 95.0% ± 3% | PASS |
| B: Analysis | 0.10 | 1,979,597 | 152,295 | 92.3% | 92.3% ± 3% | PASS |
| C: Development | 0.25 | 1,979,597 | 231,196 | 88.3% | 88.3% ± 4% | PASS |
| D: High Churn | 0.50 | 1,979,187 | 312,149 | 84.2% | 84.2% ± 5% | PASS |

See `manifest.json` for reproducibility metadata.
