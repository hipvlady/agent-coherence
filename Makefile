# Requires: pip install -e ".[langgraph,benchmark]"

.PHONY: benchmark benchmark-check help

benchmark:  ## Run all three LangGraph benchmarks and write latest.json
	python tools/run_benchmarks.py

benchmark-check:  ## Check latest.json drift against expected.json (skips benchmark run)
	python tools/benchmark_drift_check.py

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
