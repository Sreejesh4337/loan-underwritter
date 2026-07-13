from __future__ import annotations

from typing import Any

from src.db import get_run, list_runs, save_run


def append_run(record: dict[str, Any]) -> None:
    save_run(record)

__all__ = ["append_run", "get_run", "list_runs"]
