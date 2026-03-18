# agent-coherence — The Coherence Protocol for AI Agents

[![CI](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml/badge.svg)](https://github.com/hipvlady/agent-coherence/actions/workflows/ci.yml)

`agent-coherence` implements MESI-style cache coherence for shared artifacts in multi-agent LLM systems, reducing synchronization token overhead and preventing stale-context coordination failures.

## Install

```bash
pip install agent-coherence
```

## Quick start

```python
from ccs.simulation.engine import run_strategy_comparison
from ccs.simulation.scenarios import load_scenario

scenario = load_scenario("benchmarks/scenarios/planning_canonical.yaml")
report = run_strategy_comparison(scenario, strategies=["eager", "lazy"], runs=5, seed_start=20260305)
print(report.to_dict()["aggregated"])
```

## Reproduce benchmark artifacts

```bash
bash reproduce.sh
```

See [REPRODUCE.md](REPRODUCE.md) for full output mapping and baseline verification details.

## Paper

[Token Coherence: Adapting MESI Cache Protocols to Minimize Synchronization Overhead in Multi-Agent LLM Systems](https://arxiv.org/abs/2603.15183)

## License

Apache-2.0 (`LICENSE`)
