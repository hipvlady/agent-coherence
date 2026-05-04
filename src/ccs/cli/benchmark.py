"""CLI entrypoint for benchmarking a user-provided LangGraph graph factory."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccs-benchmark",
        description=(
            "Benchmark a LangGraph graph with CCSStore to measure token savings.\n"
            "\n"
            "The graph factory must accept a single `store` argument and return a\n"
            "compiled LangGraph graph (i.e. call builder.compile(store=store))."
        ),
        epilog=(
            "Install: pip install \"agent-coherence[langgraph,benchmark]\"\n"
            "\n"
            "Example:\n"
            "  ccs-benchmark --graph examples/langgraph_planner/main.py:build_graph"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--graph",
        required=True,
        metavar="PATH:FUNCTION",
        help=(
            "Path to a Python file and factory function name, separated by ':'.\n"
            "Example: path/to/my_graph.py:build_graph"
        ),
    )
    parser.add_argument(
        "--initial-state",
        default="{}",
        metavar="JSON",
        help="JSON object passed as the initial state to graph.invoke(). Default: '{}'",
    )
    return parser


def _load_factory(graph_arg: str):
    """Parse PATH:FUNCTION, load the module, and return the callable."""
    # Split on the last ':' so Windows drive letters (C:\\...) are handled correctly.
    if ":" not in graph_arg:
        print(
            f"error: --graph must be in PATH:FUNCTION format; got {graph_arg!r}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    colon_idx = graph_arg.rfind(":")
    path_str = graph_arg[:colon_idx]
    fn_name = graph_arg[colon_idx + 1:]

    graph_path = Path(path_str)
    if not graph_path.exists():
        print(f"error: graph file not found: {graph_path}", file=sys.stderr)
        raise SystemExit(1)

    # Prepend the file's directory so relative imports inside the module resolve.
    module_dir = str(graph_path.parent.resolve())
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    spec = importlib.util.spec_from_file_location("_ccs_benchmark_graph", graph_path)
    if spec is None or spec.loader is None:
        print(f"error: cannot load module from {graph_path}", file=sys.stderr)
        raise SystemExit(1)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        print(f"error: failed to import {graph_path}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    factory = getattr(module, fn_name, None)
    if factory is None:
        print(
            f"error: function {fn_name!r} not found in {graph_path}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return factory


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Parse initial state.
    try:
        initial_state = json.loads(args.initial_state)
    except json.JSONDecodeError as exc:
        print(f"error: --initial-state is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(initial_state, dict):
        print(
            f"error: --initial-state must be a JSON object (dict); got {type(initial_state).__name__}",
            file=sys.stderr,
        )
        return 1

    factory = _load_factory(args.graph)

    # Import CCSStore here so the module can be imported without langgraph installed.
    try:
        from ccs.adapters.ccsstore import CCSStore
    except ImportError as exc:
        print(
            f"error: {exc}\n"
            "Install: pip install \"agent-coherence[langgraph,benchmark]\"",
            file=sys.stderr,
        )
        return 1

    store = CCSStore(strategy="lazy", benchmark=True)

    try:
        graph = factory(store)
    except TypeError as exc:
        print(
            f"error: factory {args.graph!r} raised TypeError — "
            f"ensure it accepts a single `store` positional argument: {exc}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"error: factory raised an exception: {exc}", file=sys.stderr)
        return 1

    try:
        graph.invoke(initial_state)
    except Exception as exc:
        print(
            f"error: graph.invoke() raised an exception: {exc}\n"
            "Tip: check that --initial-state matches the graph's expected input schema.",
            file=sys.stderr,
        )
        return 1

    store.print_benchmark_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
