#!/usr/bin/env python3
"""
Convert Locust CSV stats files to Prometheus text format for the GitLab metrics artifact.

Searches results/ recursively for *_stats.csv files produced by the performance tests
and writes metrics.txt in the working directory.  Each Locust endpoint row becomes a
set of labelled gauge samples that GitLab will diff between the MR branch and main.

Usage (called from the CI job script after fetch-results):
    .gitlab-ci/locust_to_prometheus.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

OUTPUT = Path("metrics.txt")
PREFIX = "kelvin_perf"

COLUMNS = [
    ("requests_total", "Request Count", "Total HTTP requests sent"),
    ("failures_total", "Failure Count", "Total failed HTTP requests"),
    ("rps", "Requests/s", "Requests per second"),
    ("response_avg_ms", "Average Response Time", "Average response time in milliseconds"),
    ("response_p50_ms", "50%", "Median response time in milliseconds"),
    ("response_p95_ms", "95%", "95th-percentile response time in milliseconds"),
    ("response_p99_ms", "99%", "99th-percentile response time in milliseconds"),
]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def collect(stats_files: list[Path]) -> dict[str, list[str]]:
    """Return {metric_name: [sample_line, ...]} for all CSV files."""
    metric_samples: dict[str, list[str]] = defaultdict(list)
    for path in stats_files:
        print(f"Processing {path}", file=sys.stderr)
        with path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                endpoint = _escape(row["Name"])
                method = _escape(row["Type"])
                labels = f'method="{method}",endpoint="{endpoint}"'
                for suffix, col, _ in COLUMNS:
                    metric = f"{PREFIX}_{suffix}"
                    metric_samples[metric].append(f"{metric}{{{labels}}} {row[col]}")
    return metric_samples


def write_prometheus(metric_samples: dict[str, list[str]]) -> None:
    lines: list[str] = []
    descriptions = {f"{PREFIX}_{s}": desc for s, _, desc in COLUMNS}
    for metric, samples in metric_samples.items():
        lines.append(f"# HELP {metric} {descriptions[metric]}")
        lines.append(f"# TYPE {metric} gauge")
        lines.extend(samples)
        lines.append("")
    OUTPUT.write_text("\n".join(lines))
    print(f"Wrote {sum(len(v) for v in metric_samples.values())} samples to {OUTPUT}", file=sys.stderr)


def main() -> int:
    stats_files = sorted(Path("results").rglob("*_stats.csv"))
    if not stats_files:
        print(
            "No Locust *_stats.csv files found under results/ — skipping metrics export", file=sys.stderr
        )
        return 0
    metric_samples = collect(stats_files)
    write_prometheus(metric_samples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
