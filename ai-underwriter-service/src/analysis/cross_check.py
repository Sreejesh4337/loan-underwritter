"""Cross-document consistency checks and net-income source selection.

Pure Python — joins the three extracted documents, verifies basic identity
consistency, and picks the net_monthly_income source per the lending policy:
salaried -> income-sheet average net pay; self-employed -> average monthly
bank credits.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from src.analysis.metrics import average_monthly_bank_credits
from src.schemas.underwriting import EmploymentType, Transaction, TransactionCategory

DEFAULT_INCOME_TOLERANCE_PCT = 10.0

# Honorifics stripped before name comparison — they're formatting noise, not
# identity information, and different documents/extractions include them
# inconsistently.
_HONORIFICS = {"mr", "mrs", "ms", "miss", "mx", "dr", "shri", "smt", "kumari"}


@dataclass
class CrossCheckResult:
    net_monthly_income: float
    net_monthly_income_source: str  # "income_sheet" | "bank_avg_credits"
    name_consistency_ok: bool
    income_consistency_ok: bool = True
    warnings: list[str] = field(default_factory=list)


def resolve_net_monthly_income(
    *,
    employment_type: EmploymentType,
    income_sheet_average_net_pay: float | None,
    transactions: list[Transaction],
) -> tuple[float, str]:
    if employment_type == EmploymentType.SALARIED:
        if income_sheet_average_net_pay is None:
            raise ValueError("salaried applicant is missing an income-sheet average net pay figure")
        return income_sheet_average_net_pay, "income_sheet"
    return average_monthly_bank_credits(transactions), "bank_avg_credits"


def _name_tokens(name: str) -> set[str]:
    """Lowercase, strip punctuation, and drop honorifics — leaving the bare
    set of name tokens so word order, titles, and punctuation differences
    between independently-extracted documents don't register as identity
    mismatches."""
    cleaned = re.sub(r"[^\w\s]", " ", name.strip().lower())
    return {t for t in cleaned.split() if t not in _HONORIFICS}


def _names_consistent(a: set[str], b: set[str]) -> bool:
    """Two token sets are consistent if one is a subset of the other, so a
    missing middle name or an initial standing in for a full given name
    (both common across KYC/income/bank documents) isn't flagged. Bare
    single-letter initials are dropped from both sides first — otherwise
    "R Verma" vs "Rohan Verma" (same token count either way) could pick
    the wrong side as the "smaller" one to check."""
    core_a = {t for t in a if len(t) > 1} or a
    core_b = {t for t in b if len(t) > 1} or b
    smaller, larger = (core_a, core_b) if len(core_a) <= len(core_b) else (core_b, core_a)
    return bool(smaller) and smaller.issubset(larger)


def check_name_consistency(
    *,
    kyc_full_name: str,
    income_sheet_applicant_name: str,
    bank_account_holder_name: str,
) -> tuple[bool, str | None]:
    """Compare the applicant name as it appears on each of the three
    documents. Exposed standalone (in addition to being used by `cross_check`)
    so it can also be run as an upload-time / pre-extraction reject, before
    any LLM extraction is attempted."""
    names = {
        "kyc": kyc_full_name,
        "income sheet": income_sheet_applicant_name,
        "bank statement": bank_account_holder_name,
    }
    tokens = {label: _name_tokens(n) for label, n in names.items()}
    labels = list(tokens)
    ok = all(
        _names_consistent(tokens[labels[i]], tokens[labels[j]])
        for i in range(len(labels))
        for j in range(i + 1, len(labels))
    )
    if ok:
        return True, None
    return False, (
        f"applicant name mismatch across documents: KYC={kyc_full_name!r}, "
        f"income sheet={income_sheet_applicant_name!r}, bank statement={bank_account_holder_name!r}"
    )


def check_salary_consistency(
    *,
    monthly_table_header: list[str],
    monthly_rows: list[list],
    transactions: list[Transaction],
    tolerance_pct: float = DEFAULT_INCOME_TOLERANCE_PCT,
) -> tuple[bool, list[str]]:
    """Verify each income-sheet monthly net-pay row against that same calendar
    month's actual salary credits in the bank statement. A month with no
    salary credit at all, or one whose credit total differs from the
    declared net pay by more than `tolerance_pct`, is a failure."""
    if not monthly_rows:
        return True, []

    try:
        month_idx = monthly_table_header.index("Month")
        net_pay_idx = next(i for i, h in enumerate(monthly_table_header) if h.startswith("Net pay"))
    except (ValueError, StopIteration):
        return True, []

    actual_salary_by_month: dict[tuple[int, int], float] = defaultdict(float)
    for t in transactions:
        if t.category == TransactionCategory.SALARY:
            actual_salary_by_month[(t.txn_date.year, t.txn_date.month)] += t.credit

    ok = True
    warnings: list[str] = []
    for row in monthly_rows:
        month_label = str(row[month_idx]).strip()
        declared = float(row[net_pay_idx])
        try:
            parsed_month = datetime.strptime(month_label, "%b %Y")
        except ValueError:
            continue
        key = (parsed_month.year, parsed_month.month)
        actual = actual_salary_by_month.get(key)
        if actual is None:
            ok = False
            warnings.append(
                f"income sheet declares a salary of {declared:,.0f} for {month_label}, but no "
                "salary credit was found in the bank statement for that month"
            )
            continue
        diff_pct = abs(actual - declared) / declared * 100 if declared else 0.0
        if diff_pct > tolerance_pct:
            ok = False
            warnings.append(
                f"income sheet declares a salary of {declared:,.0f} for {month_label}, but the "
                f"bank statement shows {actual:,.0f} for that month ({diff_pct:.1f}% difference, "
                f"exceeding the {tolerance_pct:.0f}% tolerance)"
            )

    return ok, warnings


def cross_check(
    *,
    employment_type: EmploymentType,
    kyc_full_name: str,
    income_sheet_applicant_name: str,
    bank_account_holder_name: str,
    income_sheet_average_net_pay: float | None,
    transactions: list[Transaction],
    monthly_table_header: list[str] | None = None,
    monthly_rows: list[list] | None = None,
    tolerance_pct: float = DEFAULT_INCOME_TOLERANCE_PCT,
) -> CrossCheckResult:
    warnings: list[str] = []
    name_ok, name_error = check_name_consistency(
        kyc_full_name=kyc_full_name,
        income_sheet_applicant_name=income_sheet_applicant_name,
        bank_account_holder_name=bank_account_holder_name,
    )
    if name_error:
        warnings.append(name_error)

    income, source = resolve_net_monthly_income(
        employment_type=employment_type,
        income_sheet_average_net_pay=income_sheet_average_net_pay,
        transactions=transactions,
    )

    income_ok = True
    if employment_type == EmploymentType.SALARIED:
        income_ok, income_warnings = check_salary_consistency(
            monthly_table_header=monthly_table_header or [],
            monthly_rows=monthly_rows or [],
            transactions=transactions,
            tolerance_pct=tolerance_pct,
        )
        warnings.extend(income_warnings)

    return CrossCheckResult(
        net_monthly_income=income,
        net_monthly_income_source=source,
        name_consistency_ok=name_ok,
        income_consistency_ok=income_ok,
        warnings=warnings,
    )
