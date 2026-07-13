"""KYC/credit document extraction.

Uses a cheap-model (gpt-4o-mini) structured-output call over the document's
clean parsed text, producing Applicant + LoanRequest + CreditBureau in one
shot. Requires OPENAI_API_KEY to be set in .env.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel, Field

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model
from src.llm.pricing import estimate_cost_usd
from src.parsers.kyc_parser import ParsedKycDocument
from src.schemas.underwriting import Applicant, CreditBureau, EmploymentType, LoanRequest, StepUsage

logger = logging.getLogger(__name__)


class _KycExtractionSchema(BaseModel):
    """LLM structured-output target — flattened across the three domain
    schemas since this is genuinely one document's worth of fields."""

    full_name: str
    date_of_birth: str = Field(description="ISO format YYYY-MM-DD")
    pan_masked: str
    mobile_masked: str
    employment_type: str = Field(description='"salaried" or "self_employed"')
    employer_or_business: str
    address: str
    city: str
    state: str
    credit_score: int
    active_loans: int
    delinquencies_12m: int
    enquiries_6m: int
    product: str
    requested_amount: float
    tenor_months: int
    indicative_rate_pct: float


def extract_kyc(parsed: ParsedKycDocument, applicant_id: str) -> tuple[Applicant, LoanRequest, CreditBureau, StepUsage]:
    model = get_cheap_model().with_structured_output(_KycExtractionSchema, include_raw=True)
    prompt = (
        "Extract the applicant, loan request, and credit bureau fields from this "
        "KYC & credit summary document. Return exact values as they appear.\n\n"
        f"{parsed.raw_text}"
    )
    result = model.invoke(prompt)
    extraction: _KycExtractionSchema = result["parsed"]
    raw_message = result["raw"]
    usage_meta = getattr(raw_message, "usage_metadata", None) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    applicant = Applicant(
        applicant_id=applicant_id,
        full_name=extraction.full_name,
        date_of_birth=datetime.strptime(extraction.date_of_birth, "%Y-%m-%d").date(),
        pan_masked=extraction.pan_masked,
        mobile_masked=extraction.mobile_masked,
        employment_type=EmploymentType(extraction.employment_type.lower()),
        employer_or_business=extraction.employer_or_business,
        address=extraction.address,
        city=extraction.city,
        state=extraction.state,
    )
    loan_request = LoanRequest(
        product=extraction.product,
        requested_amount=extraction.requested_amount,
        tenor_months=extraction.tenor_months,
        indicative_rate_pct=extraction.indicative_rate_pct,
    )
    credit_bureau = CreditBureau(
        credit_score=extraction.credit_score,
        active_loans=extraction.active_loans,
        delinquencies_12m=extraction.delinquencies_12m,
        enquiries_6m=extraction.enquiries_6m,
    )
    usage = StepUsage(
        step="extract_kyc",
        model=CHEAP_MODEL_NAME,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(CHEAP_MODEL_NAME, input_tokens, output_tokens),
    )
    return applicant, loan_request, credit_bureau, usage
