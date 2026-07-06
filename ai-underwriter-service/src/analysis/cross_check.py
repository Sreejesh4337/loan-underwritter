"""Cross-document consistency checks and net-income source selection.

Pure Python — joins the three extracted documents, verifies basic identity
consistency, and picks the net_monthly_income source per the lending policy:
salaried -> income-sheet average net pay; self-employed -> average monthly
bank credits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.analysis.metrics import average_monthly_bank_credits
from src.schemas.underwriting import EmploymentType, Transaction


@dataclass
class CrossCheckResult:
    net_monthly_income: float
    net_monthly_income_source: str  # "income_sheet" | "bank_avg_credits"
    name_consistency_ok: bool
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


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def cross_check(
    *,
    employment_type: EmploymentType,
    kyc_full_name: str,
    income_sheet_applicant_name: str,
    bank_account_holder_name: str,
    income_sheet_average_net_pay: float | None,
    transactions: list[Transaction],
) -> CrossCheckResult:
    warnings: list[str] = []
    names = {
        _normalize_name(kyc_full_name),
        _normalize_name(income_sheet_applicant_name),
        _normalize_name(bank_account_holder_name),
    }
    name_ok = len(names) == 1
    if not name_ok:
        warnings.append(
            f"applicant name mismatch across documents: KYC={kyc_full_name!r}, "
            f"income sheet={income_sheet_applicant_name!r}, bank statement={bank_account_holder_name!r}"
        )

    income, source = resolve_net_monthly_income(
        employment_type=employment_type,
        income_sheet_average_net_pay=income_sheet_average_net_pay,
        transactions=transactions,
    )

    return CrossCheckResult(
        net_monthly_income=income,
        net_monthly_income_source=source,
        name_consistency_ok=name_ok,
        warnings=warnings,
    )
