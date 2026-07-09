"""Bank statement extraction — deliberately narrow.

Transaction rows are parsed 100% in code. The LLM call only handles
classifying transaction descriptions that don't match a known regex
category, batched as ONE call for every unique unmatched description.
Requires OPENAI_API_KEY to be set in .env.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model
from src.llm.pricing import estimate_cost_usd
from src.parsers.bank_statement_parser import ParsedBankStatement
from src.schemas.underwriting import StepUsage, TransactionCategory

logger = logging.getLogger(__name__)

_HEADER_RE = re.compile(r"ACCOUNT HOLDER ACCOUNT TYPE\n(.+?)\s+(Savings|Current)\b", re.IGNORECASE)


def extract_account_holder(parsed: ParsedBankStatement) -> tuple[str | None, str | None]:
    match = _HEADER_RE.search(parsed.header_text)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


class ClassificationItem(BaseModel):
    description: str
    category: str


class _ClassificationSchema(BaseModel):
    classifications: list[ClassificationItem]


def classify_unmatched_descriptions(descriptions: list[str]) -> tuple[dict[str, TransactionCategory], StepUsage]:
    """One batched cheap-model call classifying every description that fell
    through the regex categorizer, never one call per transaction row."""
    if not descriptions:
        return {}, StepUsage(step="extract_bank_statement", model="none (no unmatched descriptions)")

    model = get_cheap_model().with_structured_output(_ClassificationSchema, include_raw=True)
    categories = ", ".join(c.value for c in TransactionCategory)
    prompt = (
        f"Classify each bank transaction description into exactly one of: {categories}. "
        "Return a list containing the original description (verbatim) and its category.\n\n"
        + "\n".join(descriptions)
    )
    result = model.invoke(prompt)
    extraction: _ClassificationSchema = result["parsed"]
    usage_meta = getattr(result["raw"], "usage_metadata", None) or {}
    input_tokens = usage_meta.get("input_tokens", 0)
    output_tokens = usage_meta.get("output_tokens", 0)

    classifications = {
        item.description: TransactionCategory(item.category)
        for item in extraction.classifications
        if item.description in descriptions
    }
    for d in descriptions:
        classifications.setdefault(d, TransactionCategory.OTHER)

    usage = StepUsage(
        step="extract_bank_statement",
        model=CHEAP_MODEL_NAME,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(CHEAP_MODEL_NAME, input_tokens, output_tokens),
    )
    return classifications, usage
