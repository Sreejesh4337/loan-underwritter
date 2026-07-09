"""Income document extraction.

Uses a cheap-model (gpt-4o-mini) structured-output extraction over the
income sheet data. Requires OPENAI_API_KEY to be set in .env.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model
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


def extract_income(parsed: ParsedIncomeDocument) -> tuple[IncomeExtraction, StepUsage]:
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
        employment_type=EmploymentType(extraction.employment_type.lower()),
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
