"""A JSON-lines run registry — not a real database, deliberately, per the
plan's "demo service" scope. Append-only; readers take the latest record per
run_id, which is enough for the single-process demo this API targets."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path("data/runs_registry.jsonl")
_lock = threading.Lock()


def append_run(record: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(REGISTRY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def _all_records() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def get_run(run_id: str) -> dict[str, Any] | None:
    latest = None
    for record in _all_records():
        if record.get("run_id") == run_id:
            latest = record
    return latest


def list_runs() -> list[dict[str, Any]]:
    latest_by_id: dict[str, dict[str, Any]] = {}
    for record in _all_records():
        latest_by_id[record["run_id"]] = record
    return sorted(latest_by_id.values(), key=lambda r: r.get("created_at", ""), reverse=True)
