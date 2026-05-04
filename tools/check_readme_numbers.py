"""Pre-commit hook: verify README benchmark table values match expected.json.

Reads benchmarks/expected.json, rounds each token_reduction_pct to the nearest integer,
and checks that each rounded value appears as **NN%** in the
## Real-workload benchmarks section of README.md.

Exits 0 if all values match. Exits 1 if any value is missing, or if required files
are absent.

Usage (pre-commit invokes this automatically when expected.json or README.md is staged):
    python tools/check_readme_numbers.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_EXPECTED_PATH = _REPO_ROOT / "benchmarks" / "expected.json"
_README_PATH = _REPO_ROOT / "README.md"

_SECTION_HEADER = "## Real-workload benchmarks"
_BOLD_PCT_RE = re.compile(r"\*\*(\d+)%\*\*")


def _extract_readme_section(readme_text: str) -> str:
    """Return the text from ## Real-workload benchmarks to the next ## section."""
    start = readme_text.find(_SECTION_HEADER)
    if start == -1:
        return ""
    end = readme_text.find("\n## ", start + len(_SECTION_HEADER))
    return readme_text[start:end] if end != -1 else readme_text[start:]


def check_readme_numbers(expected_path: Path, readme_path: Path) -> bool:
    """Check that rounded expected values appear in the README table; return True if OK."""
    if not expected_path.exists():
        print(
            f"ERROR: {expected_path} not found — "
            "run `make benchmark` to establish a baseline, then commit the file.",
            file=sys.stderr,
        )
        return False

    if not readme_path.exists():
        print(f"ERROR: {readme_path} not found.", file=sys.stderr)
        return False

    workloads = json.loads(expected_path.read_text()).get("workloads", [])
    if not workloads:
        print("ERROR: expected.json contains no workloads.", file=sys.stderr)
        return False

    section = _extract_readme_section(readme_path.read_text())
    if not section:
        print(
            f"ERROR: '{_SECTION_HEADER}' section not found in README.md.",
            file=sys.stderr,
        )
        return False

    readme_pcts = {int(m) for m in _BOLD_PCT_RE.findall(section)}

    missing: list[str] = []
    for w in workloads:
        display = round(w["token_reduction_pct"])
        if display not in readme_pcts:
            missing.append(
                f"  expected **{display}%** (from '{w['name']}'"
                f" token_reduction_pct={w['token_reduction_pct']:.2f})"
                " — not found in README ## Real-workload benchmarks table"
            )

    if missing:
        print("README benchmark numbers are stale:", file=sys.stderr)
        for msg in missing:
            print(msg, file=sys.stderr)
        print(
            "\nUpdate the Savings column in README.md ## Real-workload benchmarks to match expected.json.",
            file=sys.stderr,
        )
        return False

    print("README benchmark numbers are up to date.")
    return True


def main() -> None:
    passed = check_readme_numbers(_EXPECTED_PATH, _README_PATH)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
