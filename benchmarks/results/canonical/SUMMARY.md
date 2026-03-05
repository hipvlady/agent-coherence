# Canonical Benchmark Summary — Paper §8 Table 1 Reproduction

- generated_on: 2026-03-05
- baseline: T_broadcast = n*S*m*|d| = 1,966,080 tokens
- runs_per_strategy: 10
- strategies: broadcast, lazy

| Scenario | V | T_broadcast | T_lazy | Savings | Target | Status |
|---|---|---:|---:|---:|---:|---|
| A: Planning | 0.05 | 1,979,597 | 98,055 | 95.0% | 85.0% ± 3% | FAIL |
| B: Analysis | 0.10 | 1,979,597 | 152,295 | 92.3% | 80.0% ± 3% | FAIL |
| C: Development | 0.25 | 1,979,597 | 231,196 | 88.3% | 65.0% ± 4% | FAIL |
| D: High Churn | 0.50 | 1,979,187 | 312,149 | 84.2% | 40.0% ± 5% | FAIL |

See `manifest.json` for reproducibility metadata.
