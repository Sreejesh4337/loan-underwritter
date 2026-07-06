"""LangGraph state schema.

A TypedDict, not a live Pydantic object: LangGraph's checkpointer serializes
the whole state dict every superstep, so a JSON-safe TypedDict is the robust,
DB-friendly choice. Pydantic models are used inside node functions for
validation (`.model_dump()` on write, reconstruct on read).

At the `done` node, the accumulated state is assembled into the terminal
`UnderwritingResult` Pydantic object (src/schemas/underwriting.py) — that's
the one artifact handed to the API, the eval harness, and the output
generators.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer for dict-valued channels written by multiple parallel nodes in
    the same superstep (the extract_* fan-out) — a plain (non-Annotated)
    dict field can only be written by one node per step in LangGraph."""
    merged = dict(a)
    merged.update(b)
    return merged


def _latest_timestamp(a: str, b: str) -> str:
    """ISO 8601 timestamps with a 'Z' suffix compare correctly as plain
    strings, so lexicographic max is the most recent — used because
    `updated_at` is written by every node, including the 3 parallel
    extract_* nodes in the same superstep."""
    return max(a, b)


class StepStatus(TypedDict, total=False):
    status: str  # "pending" | "running" | "done" | "failed"
    attempt_count: int
    started_at: str | None
    finished_at: str | None
    error: str | None


class UnderwritingState(TypedDict, total=False):
    # Identity
    application_id: str
    run_id: str
    thread_id: str

    # Inputs
    input_paths: dict[str, str]  # {"bank_statement": path, "kyc_and_credit": path, "income_details": path}

    # Run bookkeeping
    run_status: str  # "pending" | "running" | "completed" | "failed_input" | "failed"
    plan: list[dict[str, str]]  # [{"node": ..., "reason": ...}, ...]
    # Written by every node, including the 3 parallel extract_* nodes in the same
    # superstep -> needs a merge reducer, not last-value-wins.
    step_status: Annotated[dict[str, StepStatus], _merge_dicts]
    errors: Annotated[list[dict[str, Any]], operator.add]

    # Parsing (deterministic, no LLM) — JSON-safe dumps of the parser dataclasses,
    # keyed by document type ("kyc" | "income" | "bank_statement")
    parsed: dict[str, Any]

    # Extraction (LLM helper agents / deterministic fallback). Each of the 3
    # parallel extract_* nodes owns exactly one of these keys, so no reducer
    # is needed — a shared "extracted" dict would conflict across the fan-out.
    extracted_kyc: dict[str, Any]
    extracted_income: dict[str, Any]
    extracted_bank_statement: dict[str, Any]

    # Analysis (pure Python)
    bank_statement_summary: dict[str, Any]
    cross_check: dict[str, Any]
    metrics: dict[str, Any]

    # Decision
    policy_result: dict[str, Any]
    decision: dict[str, Any]  # {"rationale_text": ..., "advisory_notes": [...]}

    # Outputs
    outputs: dict[str, str]  # {"memo_pdf": path, "cashflow_xlsx": path, "decision_json": path}

    # Cost tracking
    token_usage: Annotated[list[dict[str, Any]], operator.add]

    created_at: str
    updated_at: Annotated[str, _latest_timestamp]


def new_step_status() -> StepStatus:
    return {"status": "pending", "attempt_count": 0, "started_at": None, "finished_at": None, "error": None}
