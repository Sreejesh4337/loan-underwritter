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


class ApplicantProfileResponse(BaseModel):
    run_id: str
    application_id: str
    applicant_id: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None
    pan_masked: str | None = None
    mobile_masked: str | None = None
    employment_type: str | None = None
    employer_or_business: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    product: str | None = None
    requested_amount: float | None = None
    tenor_months: int | None = None
    indicative_rate_pct: float | None = None
    credit_score: int | None = None
    active_loans: int | None = None
    delinquencies_12m: int | None = None
    enquiries_6m: int | None = None
    net_monthly_income: float | None = None
    net_monthly_income_source: str | None = None
    foir_pct: float | None = None
    avg_bank_balance: float | None = None
    vintage_months: int | None = None
    payment_returns_count: int | None = None
    created_at: str | None = None


class SalaryCreditResponse(BaseModel):
    txn_date: str
    description: str | None = None
    credit_amount: float | None = None
    balance: float | None = None


class DuplicateDocumentInfo(BaseModel):
    """Detail for a single document that is within the cooldown window."""

    doc_type: str
    previous_application_id: str
    processed_at: str
    cooldown_until: str
    days_remaining: int
