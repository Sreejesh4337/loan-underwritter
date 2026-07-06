"""Deterministic transaction categorization.

Regex-based against the sample data's fixed, template-generated description
vocabulary (confirmed by direct inspection of all 15 sample packets:
"Salary Credit - EMP PAYROLL", "ACH Debit - EXISTING LOAN EMI",
"ECS RETURN CHARGES - INSUFF FUNDS", "CASH DEPOSIT - BRANCH"). This is a
deliberate scoping choice, not a claim of general-purpose OCR-grade
robustness — see the project plan's stated scoping decisions. Any
description that doesn't match a known pattern falls through to the LLM
extractor's batched classification call for the small number of ambiguous
cases (see src/extractors/bank_statement_extractor.py), never per-row.
"""

from __future__ import annotations

import re

from src.parsers.bank_statement_parser import RawTransactionRow
from src.schemas.underwriting import TransactionCategory

_SALARY_RE = re.compile(r"SALARY\s+CREDIT", re.IGNORECASE)
_EMI_RE = re.compile(r"\bEMI\b", re.IGNORECASE)
_RETURN_RE = re.compile(r"RETURN|BOUNCE|DISHONOU?R|INSUFF", re.IGNORECASE)
_CASH_DEPOSIT_RE = re.compile(r"CASH\s+DEPOSIT", re.IGNORECASE)


def categorize_transaction(row: RawTransactionRow) -> TransactionCategory:
    desc = row.description
    if _RETURN_RE.search(desc):
        return TransactionCategory.RETURN
    if _SALARY_RE.search(desc) and row.credit > 0:
        return TransactionCategory.SALARY
    if _EMI_RE.search(desc) and row.debit > 0:
        return TransactionCategory.EMI
    if _CASH_DEPOSIT_RE.search(desc) and row.credit > 0:
        return TransactionCategory.CASH_DEPOSIT
    return TransactionCategory.OTHER


def unmatched_descriptions(rows: list[RawTransactionRow]) -> list[str]:
    """Unique description strings that fell through to OTHER — the small,
    deduped set that would be handed to a cheap-model classification call
    in production (batched once, never per row)."""
    seen: set[str] = set()
    for row in rows:
        if categorize_transaction(row) is TransactionCategory.OTHER:
            seen.add(row.description)
    return sorted(seen)
