"""Income document extraction.

Handles both confirmed income-sheet layouts (salaried monthly-payslip table;
self-employed business Item/Value table). The self-employed applicant's
authoritative net monthly income is NOT taken from this sheet's own declared
"Avg monthly bank credits" figure — per the lending policy, that figure is
independently computed from the bank statement itself
(src/analysis/metrics.average_monthly_bank_credits). This extractor only
recovers applicant identity, employment type, and vintage, plus the salaried
average net pay (which the policy *does* source from this sheet).
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model, llm_available
from src.llm.pricing import estimate_cost_usd
from src.parsers.income_parser import ParsedIncomeDocument
from src.schemas.underwriting import EmploymentType, StepUsage

logger = logging.getLogger(__name__)


class IncomeExtraction(BaseModel):
    applicant_name: str
    employment_type: EmploymentType
    employer_or_business: str
    vintage_months: int
    average_net_pay: float | None = None  # salaried only


class _IncomeExtractionSchema(BaseModel):
    applicant_name: str
    employment_type: str = Field(description='"salaried" or "self_employed"')
    employer_or_business: str
    vintage_months: int
    average_net_pay: float | None = None


def _render_for_llm(parsed: ParsedIncomeDocument) -> str:
    lines = [f"{k}: {v}" for k, v in parsed.header_fields.items()]
    if parsed.monthly_rows:
        lines.append(f"Monthly table header: {parsed.monthly_table_header}")
        lines.extend(f"  {row}" for row in parsed.monthly_rows)
        lines.append(f"Average net pay: {parsed.average_net_pay}")
    if parsed.business_items:
        lines.extend(f"{k}: {v}" for k, v in parsed.business_items.items())
    return "\n".join(lines)


def _vintage_from_header(header_fields: dict[str, str]) -> int:
    raw = header_fields.get("Months at current job") or header_fields.get("Months in business")
    if raw is None:
        raise ValueError("income sheet header is missing a vintage field")
    return int(re.sub(r"[^\d]", "", raw))


def _extract_deterministic(parsed: ParsedIncomeDocument) -> IncomeExtraction:
    h = parsed.header_fields
    employment_type = (
        EmploymentType.SALARIED if h.get("Employment type", "").strip().lower() == "salaried" else EmploymentType.SELF_EMPLOYED
    )
    return IncomeExtraction(
        applicant_name=h["Applicant"],
        employment_type=employment_type,
        employer_or_business=h.get("Employer") or h.get("Business name") or "",
        vintage_months=_vintage_from_header(h),
        average_net_pay=parsed.average_net_pay,
    )


def _extract_llm(parsed: ParsedIncomeDocument) -> tuple[IncomeExtraction, StepUsage]:
    model = get_cheap_model().with_structured_output(_IncomeExtractionSchema, include_raw=True)
    prompt = (
        "Extract the applicant's employment details from this income sheet. "
        'employment_type must be exactly "salaried" or "self_employed".\n\n'
        f"{_render_for_llm(parsed)}"
    )
    result = model.invoke(prompt)
    extraction: _IncomeExtractionSchema = result["parsed"]
    usage_meta = getattr(result["raw"], "usage_metadata", None) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    income = IncomeExtraction(
        applicant_name=extraction.applicant_name,
        employment_type=EmploymentType(extraction.employment_type),
        employer_or_business=extraction.employer_or_business,
        vintage_months=extraction.vintage_months,
        average_net_pay=extraction.average_net_pay,
    )
    usage = StepUsage(
        step="extract_income",
        model=CHEAP_MODEL_NAME,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(CHEAP_MODEL_NAME, input_tokens, output_tokens),
    )
    return income, usage


def extract_income(parsed: ParsedIncomeDocument) -> tuple[IncomeExtraction, StepUsage]:
    if llm_available():
        try:
            return _extract_llm(parsed)
        except Exception as exc:
            logger.warning("LLM income extraction failed (%s); falling back to deterministic parsing", exc)

    return _extract_deterministic(parsed), StepUsage(step="extract_income", model="deterministic-fallback")
