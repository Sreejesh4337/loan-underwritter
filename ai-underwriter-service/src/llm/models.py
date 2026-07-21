"""Model routing — the single, auditable place that answers "which model per
step, and why" for the report.

Cheap model (gpt-4o-mini): structured-output extraction over small, clean
parsed text (KYC, income sheet, bank-statement header block) and batched
classification of any transaction description that doesn't match a known
regex category.

Strong model (gpt-4o): the decision-rationale narrative only — it never has
authority to change the deterministic policy engine's decision (see
src/policy_engine/engine.py's module docstring for why).

Both are lazily constructed (not at import time) so this module can be
imported — and the deterministic fallback extractors can run — even when
OPENAI_API_KEY is unset, which is the default state of this sandbox.
"""

from __future__ import annotations

import os
from functools import lru_cache

CHEAP_MODEL_NAME = os.environ.get("CHEAP_MODEL_NAME", "gpt-4o-mini")
STRONG_MODEL_NAME = os.environ.get("STRONG_MODEL_NAME", "gpt-4o")

NODE_MODEL_MAP = {
    "extract_income": "cheap",
    "extract_kyc": "cheap",
    "extract_bank_statement": "cheap",
    "merge_and_cross_check": "cheap",  # only for the optional large-deposit materiality judgment
    "llm_evaluate_policy": "strong",   # reads policy YAML + metrics → decision + rationale
}


def llm_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


@lru_cache(maxsize=1)
def get_cheap_model():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=CHEAP_MODEL_NAME, temperature=0)


@lru_cache(maxsize=1)
def get_strong_model():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=STRONG_MODEL_NAME, temperature=0.2)
