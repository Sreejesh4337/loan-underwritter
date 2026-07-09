"""Request/response models for the FastAPI service — kept minimal, per the
plan's "demo service, not production" scope."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunCreateResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str


class RunStatusResponse(BaseModel):
    run_id: str
    thread_id: str
    application_id: str
    status: str
    current_step: str | None = None
    step_status: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    updated_at: str | None = None
    applicant_name: str | None = None
    decision: str | None = None


class UploadResponse(BaseModel):
    application_id: str
    run_id: str
    thread_id: str
    status: str
