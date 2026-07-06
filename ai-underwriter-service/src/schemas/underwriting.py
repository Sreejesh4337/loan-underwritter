"""Shared data contract for the underwriting pipeline.

This module is the single source of truth for the shapes that flow between the
LangGraph orchestration layer, the extractors, the policy engine, the output
generators ("skills"), the FastAPI service, and the eval harness. Nothing
downstream of the graph should redefine an equivalent shape.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class EmploymentType(str, Enum):
    SALARIED = "salaried"
    SELF_EMPLOYED = "self_employed"


class Decision(str, Enum):
    APPROVE = "approve"
    REFER = "refer"
    DECLINE = "decline"


class RuleTier(str, Enum):
    DECLINE = "decline"
    REFER = "refer"
    APPROVE = "approve"
    OVERRIDE = "override"


class TransactionCategory(str, Enum):
    SALARY = "salary"
    EMI = "emi"
    RETURN = "return"
    CASH_DEPOSIT = "cash_deposit"
    OTHER = "other"


class Applicant(BaseModel):
    applicant_id: str
    full_name: str
    date_of_birth: date | None = None
    pan_masked: str | None = None
    mobile_masked: str | None = None
    employment_type: EmploymentType
    employer_or_business: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None


class LoanRequest(BaseModel):
    product: str
    requested_amount: float
    tenor_months: int
    indicative_rate_pct: float


class CreditBureau(BaseModel):
    credit_score: int
    active_loans: int = 0
    delinquencies_12m: int = 0
    enquiries_6m: int = 0


class Transaction(BaseModel):
    txn_date: date
    description: str
    debit: float = 0.0
    credit: float = 0.0
    balance: float
    category: TransactionCategory = TransactionCategory.OTHER


class FinancialMetrics(BaseModel):
    net_monthly_income: float
    net_monthly_income_source: str  # "income_sheet" | "bank_avg_credits"
    existing_emis: float
    proposed_emi: float
    foir_pct: float
    avg_bank_balance: float
    payment_returns_count: int
    salary_credit_months_count: int | None = None  # None for self-employed
    vintage_months: int
    unexplained_cash_deposit_flag: bool = False


class FiredRule(BaseModel):
    rule_id: str
    tier: RuleTier
    message: str
    fired: bool = True


class StepUsage(BaseModel):
    step: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class RunUsage(BaseModel):
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    per_step: list[StepUsage] = Field(default_factory=list)


class UnderwritingResult(BaseModel):
    """The terminal output of a single application run.

    Consumed identically by the API layer, the eval harness, and both output
    generators (memo PDF, cash-flow Excel).
    """

    application_id: str
    run_id: str
    thread_id: str
    applicant: Applicant
    loan_request: LoanRequest
    credit_bureau: CreditBureau
    metrics: FinancialMetrics
    transactions: list[Transaction]
    decision: Decision
    fired_rules: list[FiredRule]
    rationale_text: str = ""
    advisory_notes: list[str] = Field(default_factory=list)
    generated_at: datetime
    usage: RunUsage = Field(default_factory=RunUsage)
