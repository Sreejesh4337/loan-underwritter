"""Bank statement extraction — deliberately narrow.

Per the project plan's resolved scoping decision: Python already parses
every transaction row deterministically (src/parsers/bank_statement_parser.py)
and categorizes it via regex (src/analysis/categorize.py) — running an LLM
over 20+ raw rows per statement would be exactly the token waste the brief's
cost-minimization section calls out. This module only handles:

1. The small header key/value block (account holder, account type) — used
   for the cross-document name-consistency check, not for any policy figure.
   Simple enough that a fixed regex is both correct and cheaper than an LLM
   call, so no LLM path is offered here at all.
2. Classifying transaction descriptions that don't match a known regex
   category, batched as ONE call for every unique unmatched description
   across the whole statement — never one call per row.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from src.llm.models import CHEAP_MODEL_NAME, get_cheap_model, llm_available
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


class _ClassificationSchema(BaseModel):
    classifications: dict[str, str]  # description -> one of TransactionCategory values


def classify_unmatched_descriptions(descriptions: list[str]) -> tuple[dict[str, TransactionCategory], StepUsage]:
    """One batched cheap-model call classifying every description that fell
    through the regex categorizer, never one call per transaction row."""
    if not descriptions:
        return {}, StepUsage(step="extract_bank_statement", model="none (no unmatched descriptions)")

    if not llm_available():
        return {d: TransactionCategory.OTHER for d in descriptions}, StepUsage(
            step="extract_bank_statement", model="deterministic-fallback"
        )

    try:
        model = get_cheap_model().with_structured_output(_ClassificationSchema, include_raw=True)
        categories = ", ".join(c.value for c in TransactionCategory)
        prompt = (
            f"Classify each bank transaction description into exactly one of: {categories}. "
            "Return a mapping from each input description (verbatim) to its category.\n\n"
            + "\n".join(descriptions)
        )
        result = model.invoke(prompt)
        extraction: _ClassificationSchema = result["parsed"]
        usage_meta = getattr(result["raw"], "usage_metadata", None) or {}
        input_tokens = usage_meta.get("input_tokens", 0)
        output_tokens = usage_meta.get("output_tokens", 0)

        classifications = {
            desc: TransactionCategory(cat) for desc, cat in extraction.classifications.items() if desc in descriptions
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
    except Exception as exc:
        logger.warning("LLM description classification failed (%s); leaving descriptions as OTHER", exc)
        return {d: TransactionCategory.OTHER for d in descriptions}, StepUsage(
            step="extract_bank_statement", model="deterministic-fallback"
        )
