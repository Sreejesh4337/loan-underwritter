"""Derive eval/fixtures/APP-*.expected.yaml for all 15 sample applications.

Deliberately uses an INDEPENDENT extraction path from the production pipeline
(src/extractors/, src/parsers/bank_statement_parser.py's word-position table
algorithm) — plain-text regex scanning instead of word-position column
detection. Reusing the exact same extraction code the graph runs on would let
a systematic bug in that code "confirm itself" as correct ground truth. The
one thing this script does NOT reimplement is the policy decision logic
itself: it feeds independently-derived numbers into the real
src/policy_engine/engine.py, because the ground truth we want is "what does
our actual policy engine decide given correct inputs," not a second
hand-rolled policy implementation that could itself drift from
LENDING_POLICY.pdf.

Run: python -m scripts.derive_ground_truth
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber
import yaml

from src.analysis.metrics import calculate_emi, calculate_foir_pct
from src.policy_engine.engine import evaluate
from src.schemas.underwriting import EmploymentType, FinancialMetrics

APPS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "applications"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "eval" / "fixtures"

# Apps directly hand-verified against the raw PDFs during development (see
# the project's design/implementation notes) — spot-checked across every
# rule branch: a clean decline (APP-010), the decline/refer return-count
# boundary (APP-008 vs APP-012), the high-income override candidate
# (APP-013), the self-employed path (APP-014), and the unexplained-deposit
# trigger (APP-015).
REVIEWED_APPS = {"APP-001", "APP-008", "APP-009", "APP-010", "APP-012", "APP-013", "APP-014", "APP-015"}


def _independent_kyc_fields(text: str) -> dict:
    """Plain regex over raw extracted text — independent of
    src/parsers/kyc_parser.py's word-position column detection."""
    return {
        "credit_score": int(re.search(r"CREDIT SCORE.*\n(\d+)", text).group(1)),
        "requested_amount": float(re.search(r"REQUESTED AMOUNT.*\n.*INR ([\d,]+)", text).group(1).replace(",", "")),
        "tenor_months": int(re.search(r"TENOR.*\n(\d+)", text).group(1)),
        "indicative_rate_pct": float(re.search(r"INDICATIVE RATE.*\n.*?([\d.]+)%", text, re.DOTALL).group(1)),
        "employment_type": (
            EmploymentType.SALARIED
            if re.search(r"EMPLOYMENT TYPE.*\n(\w+)", text).group(1).lower() == "salaried"
            else EmploymentType.SELF_EMPLOYED
        ),
    }


_FULL_ROW_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(.+)$")
_DATE_ONLY_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})$")
_BARE_YEAR_RE = re.compile(r"^\d{4}$")
_AMOUNT_RE = re.compile(r"^-?[\d,]+(?:\.\d+)?$")


def _independent_bank_statement_metrics(text: str) -> dict:
    """Line-based regex scanning over plain extracted text — independent of
    the production word-position table parser. Handles two confirmed row
    shapes: a complete single line ("19 Jul 2025 ECS RETURN ... 590 69,261",
    seen in most sample apps) and a date wrapped across three lines
    ("05 Aug" / body / "2025", seen in APP-001) — this appears to depend on
    per-application description length, not a single fixed template."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]  # noqa: E741

    salary_months: set[tuple[int, int]] = set()
    return_count = 0
    cash_deposits: list[float] = []
    month_end_balance: dict[tuple[int, int], float] = {}
    credit_totals: dict[tuple[int, int], float] = {}
    # Text mode collapses the Debit/Credit columns into one trailing amount;
    # a line is treated as a credit (for the self-employed average-credits
    # figure) unless it matches a known debit-type keyword — approximating
    # what the production parser reads directly off the Credit column.
    _debit_keywords = re.compile(r"EMI|UTILITIES|HOUSEHOLD|RETURN|BOUNCE|DISHONOU?R|INSUFF", re.IGNORECASE)

    def record_row(year_month: tuple[int, int], body: str) -> None:
        nonlocal return_count
        trailing_numeric = [t for t in body.split() if _AMOUNT_RE.match(t)]
        if len(trailing_numeric) < 2:
            return  # not a real transaction line (e.g. a stray footer fragment)
        amount = float(trailing_numeric[0].replace(",", ""))
        balance = float(trailing_numeric[-1].replace(",", ""))
        month_end_balance[year_month] = balance  # last write per month wins (lines are chronological)
        if "SALARY" in body.upper():
            salary_months.add(year_month)
        if re.search(r"RETURN|BOUNCE|DISHONOU?R|INSUFF", body, re.IGNORECASE):
            return_count += 1
        if "CASH DEPOSIT" in body.upper():
            cash_deposits.append(amount)
        if not _debit_keywords.search(body):
            credit_totals[year_month] = credit_totals.get(year_month, 0.0) + amount

    pending_date: tuple[str, str] | None = None  # (day, month_abbrev) awaiting a body line
    pending_body: tuple[tuple[str, str], str] | None = None  # ((day, month_abbrev), body) awaiting a year line

    for line in lines:
        full = _FULL_ROW_RE.match(line)
        if full:
            day, mon, year, body = full.groups()
            record_row((int(year), _month_num(mon)), body)
            continue

        date_only = _DATE_ONLY_RE.match(line)
        if date_only:
            pending_date = date_only.groups()
            continue

        if _BARE_YEAR_RE.match(line) and pending_body is not None:
            (day, mon), body = pending_body
            record_row((int(line), _month_num(mon)), body)
            pending_body = None
            continue

        if pending_date is not None:
            pending_body = (pending_date, line)
            pending_date = None

    return {
        "salary_credit_months_count": len(salary_months),
        "payment_returns_count": return_count,
        "avg_bank_balance": sum(month_end_balance.values()) / len(month_end_balance) if month_end_balance else 0.0,
        "avg_monthly_credits": sum(credit_totals.values()) / len(credit_totals) if credit_totals else 0.0,
        "cash_deposits": cash_deposits,
        "n_months": len(month_end_balance),
    }


def _month_num(abbrev: str) -> int:
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(abbrev[:3]) + 1


def _income_sheet_fields(path: Path) -> dict:
    # No independent alternative for reading an .xlsx cell grid — openpyxl
    # direct access has no real ambiguity to independently cross-check.
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    header = {}
    average_net_pay = None
    business_items = {}
    for row in ws.iter_rows(values_only=True):
        cells = [c for c in row if c is not None]
        if len(cells) == 2:
            key, val = str(cells[0]).strip(), cells[1]
            if key == "Average net pay":
                average_net_pay = float(val)
            elif key not in ("Month",):
                (business_items if key in ("Item",) else header).setdefault(key, val)
    vintage = header.get("Months at current job") or header.get("Months in business")
    return {"vintage_months": int(re.sub(r"[^\d]", "", str(vintage))), "average_net_pay": average_net_pay}


def derive_one(app_id: str) -> dict:
    app_dir = APPS_DIR / app_id
    with pdfplumber.open(app_dir / "kyc_and_credit.pdf") as pdf:
        kyc_text = pdf.pages[0].extract_text() or ""
    with pdfplumber.open(app_dir / "bank_statement.pdf") as pdf:
        bs_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    kyc = _independent_kyc_fields(kyc_text)
    bs = _independent_bank_statement_metrics(bs_text)
    income = _income_sheet_fields(app_dir / "income_details.xlsx")

    income_tolerance_pct = 2
    if kyc["employment_type"] == EmploymentType.SALARIED:
        net_income = income["average_net_pay"]
        income_source = "income_sheet"
        salary_months = bs["salary_credit_months_count"]
    else:
        # Self-employed: average monthly bank credits, approximated by
        # summing every transaction line NOT matching a known debit keyword
        # (EMI/UTILITIES/HOUSEHOLD/RETURN) — a coarser approximation than the
        # production parser's direct Credit-column read, so given a wider
        # tolerance below rather than treated as exact.
        net_income = bs["avg_monthly_credits"]
        income_source = "bank_avg_credits"
        salary_months = None
        income_tolerance_pct = 10

    result = {
        "app_id": app_id,
        "confidence": "reviewed" if app_id in REVIEWED_APPS else "draft",
        "notes": "derived by scripts/derive_ground_truth.py",
    }

    proposed_emi = calculate_emi(kyc["requested_amount"], kyc["indicative_rate_pct"], kyc["tenor_months"])
    # Existing EMI: independently spot the recurring debit amount via regex.
    emi_amounts = re.findall(r"EXISTING LOAN EMI\D+([\d,]+)", bs_text)
    existing_emi = float(emi_amounts[0].replace(",", "")) if emi_amounts else 0.0
    foir_pct = calculate_foir_pct(existing_emi, proposed_emi, net_income)
    unexplained_deposit = any(d > 0.5 * net_income for d in bs["cash_deposits"])

    metrics = FinancialMetrics(
        net_monthly_income=net_income,
        net_monthly_income_source=income_source,
        existing_emis=existing_emi,
        proposed_emi=proposed_emi,
        foir_pct=foir_pct,
        avg_bank_balance=bs["avg_bank_balance"],
        payment_returns_count=bs["payment_returns_count"],
        salary_credit_months_count=salary_months,
        vintage_months=income["vintage_months"],
        unexplained_cash_deposit_flag=unexplained_deposit,
    )
    policy_eval = evaluate(metrics, kyc["credit_score"])

    result.update(
        {
            "expected_decision": policy_eval.decision.value,
            "expected_fired_rule_ids": [r.rule_id for r in policy_eval.fired_rules if r.fired],
            "expected_metrics": {
                "credit_score": {"value": kyc["credit_score"], "tolerance_abs": 0},
                "net_monthly_income": {"value": round(net_income, 0), "tolerance_pct": income_tolerance_pct},
                "foir_pct": {"value": round(foir_pct, 1), "tolerance_abs": 1.5},
                "payment_returns_count": {"value": bs["payment_returns_count"], "tolerance_abs": 0},
                "avg_bank_balance": {"value": round(bs["avg_bank_balance"], 0), "tolerance_pct": 5},
                "vintage_months": {"value": income["vintage_months"], "tolerance_abs": 0},
            },
        }
    )
    return result


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    app_ids = sorted(p.name for p in APPS_DIR.iterdir() if p.name.startswith("APP-"))

    for app_id in app_ids:
        fixture = derive_one(app_id)
        out_path = FIXTURES_DIR / f"{app_id}.expected.yaml"
        with open(out_path, "w") as f:
            yaml.safe_dump(fixture, f, sort_keys=False)
        print(f"{app_id}: {fixture.get('expected_decision')} ({fixture['confidence']}) -> {out_path}")


if __name__ == "__main__":
    main()
