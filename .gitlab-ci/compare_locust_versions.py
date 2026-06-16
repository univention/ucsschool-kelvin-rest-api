#!/usr/bin/env python3
"""
Quick v1-vs-v2 comparison of Locust performance results.

When the performance tests run with ``UCS_ENV_KELVIN_API_VERSION=both`` (or
``--api-version both``) every test writes a version-suffixed stats file, e.g.
``010-get-all-users-v1_stats.csv`` and ``010-get-all-users-v2_stats.csv``.

This script pairs those files by their common base name, reads the Locust
``Aggregated`` row from each (every test exercises a single endpoint, so the
aggregate is that endpoint's summary) and prints a per-metric comparison table
in Markdown — readable in a terminal and pasteable into a merge request.

It is intentionally stdlib-only and meant as a stop-gap until results are
shipped to Prometheus/Grafana (see ``locust_to_prometheus.py``).

Usage:
    .gitlab-ci/compare_locust_versions.py [RESULTS_DIR]

RESULTS_DIR defaults to ``results`` (CI layout) and falls back to the on-host
``/var/lib/ucs-test-ucsschool-kelvin-performance/results``.
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

# (column in CSV, label, "higher is better"?)
METRICS = [
    ("Requests/s", "Requests/s", True),
    ("Average Response Time", "Avg (ms)", False),
    ("50%", "p50 (ms)", False),
    ("95%", "p95 (ms)", False),
    ("99%", "p99 (ms)", False),
    ("Failure Count", "Failures", False),
]

VERSION_SUFFIX = re.compile(r"-(?P<version>v\d+)$")
DEFAULT_DIRS = [Path("results"), Path("/var/lib/ucs-test-ucsschool-kelvin-performance/results")]


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # Locust writes "N/A" for percentiles when no requests were made


def _aggregated_row(csv_file: Path) -> dict[str, str] | None:
    with csv_file.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("Name") == "Aggregated":
                return row
    return None


def collect(results_dir: Path) -> dict[str, dict[str, dict[str, str]]]:
    """Return {test_name: {version: aggregated_row}} for all paired stats files."""
    by_test: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for csv_file in sorted(results_dir.rglob("*_stats.csv")):
        stem = csv_file.name[: -len("_stats.csv")]
        match = VERSION_SUFFIX.search(stem)
        if not match:
            # Unversioned file (e.g. from an old run) — nothing to compare against.
            continue
        version = match.group("version")
        test_name = stem[: match.start()]
        row = _aggregated_row(csv_file)
        if row is not None:
            by_test[test_name][version] = row
    return by_test


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0f}" if value >= 100 else f"{value:.2f}"


def _delta(v1: float | None, v2: float | None, higher_is_better: bool) -> str:
    if v1 is None or v2 is None:
        return "n/a"
    if v1 == 0:
        return "n/a" if v2 == 0 else "new"
    pct = (v2 - v1) / v1 * 100
    improved = (v2 > v1) if higher_is_better else (v2 < v1)
    marker = "" if abs(pct) < 0.5 else ("✅" if improved else "⚠️")
    return f"{pct:+.1f}% {marker}".strip()


def render(by_test: dict[str, dict[str, dict[str, str]]]) -> str:
    lines: list[str] = ["# Kelvin performance: v1 vs v2", ""]
    comparable = {t: v for t, v in by_test.items() if "v1" in v and "v2" in v}
    if not comparable:
        lines.append("_No test had both a v1 and a v2 stats file to compare._")
        return "\n".join(lines)

    for column, label, higher_is_better in METRICS:
        hint = "higher is better" if higher_is_better else "lower is better"
        lines += [f"## {label} ({hint})", "", "| Test | v1 | v2 | Δ |", "| --- | ---: | ---: | ---: |"]
        for test_name in sorted(comparable):
            versions = comparable[test_name]
            v1 = _to_float(versions["v1"].get(column))
            v2 = _to_float(versions["v2"].get(column))
            lines.append(
                f"| {test_name} | {_fmt(v1)} | {_fmt(v2)} | {_delta(v1, v2, higher_is_better)} |"
            )
        lines.append("")

    only_one = {t: sorted(v) for t, v in by_test.items() if not ("v1" in v and "v2" in v)}
    if only_one:
        lines.append(
            "> Tests with results for only one version (not compared): "
            + ", ".join(f"{t} ({'/'.join(vs)})" for t, vs in sorted(only_one.items()))
        )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) > 1:
        results_dir = Path(sys.argv[1])
    else:
        results_dir = next((d for d in DEFAULT_DIRS if d.is_dir()), DEFAULT_DIRS[0])
    if not results_dir.is_dir():
        print(f"Results directory {results_dir!s} not found.", file=sys.stderr)
        return 1
    print(render(collect(results_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
