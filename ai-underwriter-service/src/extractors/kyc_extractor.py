"""KYC/credit document extraction.

Per the project brief's explicit "helper agent per document (small model)"
ask: the primary path is a single cheap-model structured-output call over
the document's clean parsed text, producing Applicant + LoanRequest +
CreditBureau in one shot. When no LLM is configured (OPENAI_API_KEY unset —
the default state of this sandbox) or the call fails validation, this falls
back to a fully deterministic mapping off the parser's already-recovered
label/value pairs (see src/parsers/kyc_parser.py) — the document's layout is
an unambiguous fixed grid, so this fallback is exact, not approximate.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from pydantic import BaseModel, Field

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model, llm_available
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


def _parse_money(text: str) -> float:
    return float(re.sub(r"[^\d.]", "", text))


def _parse_int(text: str) -> int:
    return int(re.sub(r"[^\d]", "", text))


def _parse_pct(text: str) -> float:
    match = re.search(r"[\d.]+", text)
    if not match:
        raise ValueError(f"could not parse a percentage out of {text!r}")
    return float(match.group())


def _extract_deterministic(parsed: ParsedKycDocument, applicant_id: str) -> tuple[Applicant, LoanRequest, CreditBureau]:
    p = parsed.label_value_pairs
    if not p:
        raise ValueError("no label/value pairs available for deterministic KYC extraction")

    employment_type = (
        EmploymentType.SALARIED if p["EMPLOYMENT TYPE"].strip().lower() == "salaried" else EmploymentType.SELF_EMPLOYED
    )
    city_state = [s.strip() for s in p["CITY / STATE"].split(",", 1)]

    applicant = Applicant(
        applicant_id=applicant_id,
        full_name=p["FULL NAME"],
        date_of_birth=datetime.strptime(p["DATE OF BIRTH"], "%d %b %Y").date(),
        pan_masked=p["PAN (MASKED)"],
        mobile_masked=p["MOBILE (MASKED)"],
        employment_type=employment_type,
        employer_or_business=p["EMPLOYER / BUSINESS"],
        address=p["ADDRESS"],
        city=city_state[0] if city_state else None,
        state=city_state[1] if len(city_state) > 1 else None,
    )
    loan_request = LoanRequest(
        product=p["PRODUCT"],
        requested_amount=_parse_money(p["REQUESTED AMOUNT"]),
        tenor_months=_parse_int(p["TENOR"]),
        indicative_rate_pct=_parse_pct(p["INDICATIVE RATE"]),
    )
    credit_bureau = CreditBureau(
        credit_score=_parse_int(p["CREDIT SCORE"]),
        active_loans=_parse_int(p["ACTIVE LOANS"]),
        delinquencies_12m=_parse_int(p["PAST 12M DELINQUENCIES"]),
        enquiries_6m=_parse_int(p["ENQUIRIES (6M)"]),
    )
    return applicant, loan_request, credit_bureau


def _extract_llm(
    parsed: ParsedKycDocument, applicant_id: str
) -> tuple[Applicant, LoanRequest, CreditBureau, StepUsage]:
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
        employment_type=EmploymentType(extraction.employment_type),
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


def extract_kyc(parsed: ParsedKycDocument, applicant_id: str) -> tuple[Applicant, LoanRequest, CreditBureau, StepUsage]:
    if llm_available():
        try:
            return _extract_llm(parsed, applicant_id)
        except Exception as exc:
            logger.warning("LLM KYC extraction failed (%s); falling back to deterministic parsing", exc)

    applicant, loan_request, credit_bureau = _extract_deterministic(parsed, applicant_id)
    return applicant, loan_request, credit_bureau, StepUsage(step="extract_kyc", model="deterministic-fallback")
