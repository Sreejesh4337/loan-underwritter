"""Diff two eval report JSONs to produce the "before-and-after on tokens and
cost from your clean-up pass" report deliverable.

    python -m eval.compare_runs eval/reports/run_before.json eval/reports/run_after.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two eval reports")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()

    before = json.loads(args.before.read_text())["summary"]
    after = json.loads(args.after.read_text())["summary"]

    table = Table(title="Before / After Comparison")
    table.add_column("Metric")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Change")

    def row(label: str, key: str, fmt: str = "{:.4f}") -> None:
        b, a = before.get(key, 0), after.get(key, 0)
        change = f"{(a - b) / b * 100:+.1f}%" if b else "n/a"
        table.add_row(label, fmt.format(b), fmt.format(a), change)

    row("Decision accuracy", "decision_accuracy", "{:.1%}")
    row("Total tokens", "total_tokens", "{:.0f}")
    row("Total cost (USD)", "total_cost_usd", "${:.4f}")
    row("Mean duration (s)", "mean_duration_s", "{:.2f}")

    console.print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
