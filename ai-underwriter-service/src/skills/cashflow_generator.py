"""Cash-flow summary Excel generator.

A plain, deterministic Python function (see memo_generator.py's docstring
for the "skills as functions, not literal Skill folders" rationale). The
Summary sheet's ratio cells are formulas referencing the Monthly Trend
sheet, which is itself formulas referencing the raw Transactions sheet — so
a human opening the workbook can audit and recompute it, not just read a
static report. The *decision itself* is never derived from these formulas;
Python's src/analysis/metrics.py independently computes the authoritative
figures used for the actual policy evaluation.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.schemas.underwriting import TransactionCategory, UnderwritingResult
from src.skills.styles import BADGE_FILL_HEX

_HEADER_FILL = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
_HEADER_FONT = Font(bold=True)


def _write_transactions_sheet(wb: Workbook, result: UnderwritingResult):
    ws = wb.create_sheet("Transactions")
    headers = ["Date", "Description", "Debit", "Credit", "Balance", "Category"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT

    for t in sorted(result.transactions, key=lambda t: t.txn_date):
        ws.append([t.txn_date, t.description, t.debit or None, t.credit or None, t.balance, t.category.value])

    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 40
    for col in "CDEF":
        ws.column_dimensions[col].width = 14
    return ws


def _month_bounds(transactions) -> list[tuple[str, "date", "date"]]:  # noqa: F821 (date imported lazily below)
    from calendar import monthrange
    from datetime import date

    months = sorted({(t.txn_date.year, t.txn_date.month) for t in transactions})
    bounds = []
    for year, month in months:
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        bounds.append((start.strftime("%b %Y"), start, end))
    return bounds


def _write_monthly_trend_sheet(wb: Workbook, result: UnderwritingResult, n_transactions: int) -> tuple["Workbook", int]:
    ws = wb.create_sheet("Monthly Trend")
    headers = ["Month", "Month Start", "Month End", "Total Credits", "Total Debits", "Salary Credits", "EMI Debits", "Month-End Balance"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT

    last_txn_row = n_transactions + 1  # +1 for the Transactions header row
    txn_range = lambda col: f"Transactions!{col}2:{col}{last_txn_row}"  # noqa: E731

    for i, (label, start, end) in enumerate(_month_bounds(result.transactions), start=2):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=start)
        ws.cell(row=i, column=3, value=end)
        b, c = f"B{i}", f"C{i}"
        ws.cell(row=i, column=4, value=f'=SUMIFS({txn_range("D")},{txn_range("A")},">="&{b},{txn_range("A")},"<="&{c})')
        ws.cell(row=i, column=5, value=f'=SUMIFS({txn_range("C")},{txn_range("A")},">="&{b},{txn_range("A")},"<="&{c})')
        ws.cell(
            row=i,
            column=6,
            value=(
                f'=SUMIFS({txn_range("D")},{txn_range("A")},">="&{b},{txn_range("A")},"<="&{c},'
                f'{txn_range("F")},"{TransactionCategory.SALARY.value}")'
            ),
        )
        ws.cell(
            row=i,
            column=7,
            value=(
                f'=SUMIFS({txn_range("C")},{txn_range("A")},">="&{b},{txn_range("A")},"<="&{c},'
                f'{txn_range("F")},"{TransactionCategory.EMI.value}")'
            ),
        )
        ws.cell(
            row=i,
            column=8,
            value=(
                f'=INDEX({txn_range("E")},MATCH(MAXIFS({txn_range("A")},{txn_range("A")},">="&{b},'
                f'{txn_range("A")},"<="&{c}),{txn_range("A")},0))'
            ),
        )

    ws.column_dimensions["A"].width = 12
    for col in "BCDEFGH":
        ws.column_dimensions[col].width = 14

    n_months = i - 1 if result.transactions else 0
    return ws, n_months


def _write_summary_sheet(wb: Workbook, result: UnderwritingResult, n_months: int):
    ws = wb.create_sheet("Summary", 0)  # index 0 -> first/active sheet
    m = result.metrics
    trend_range = lambda col: f"'Monthly Trend'!{col}2:{col}{n_months + 1}"  # noqa: E731

    ws.append(["Cash-Flow Summary"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])

    def kv(label, value):
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = _HEADER_FONT

    kv("Applicant", result.applicant.full_name)
    kv("Application ID", result.application_id)
    kv("Employment type", result.applicant.employment_type.value)

    income_row = ws.max_row + 1
    if m.net_monthly_income_source == "bank_avg_credits":
        kv("Net monthly income (avg monthly bank credits)", f"=AVERAGE({trend_range('D')})")
    else:
        kv("Net monthly income (income sheet)", m.net_monthly_income)

    existing_emi_row = ws.max_row + 1
    kv("Existing EMIs (avg/month)", f"=AVERAGE({trend_range('G')})")

    proposed_emi_row = ws.max_row + 1
    kv("Proposed EMI", m.proposed_emi)

    foir_row = ws.max_row + 1
    kv("FOIR", f"=(B{existing_emi_row}+B{proposed_emi_row})/B{income_row}")
    ws.cell(row=foir_row, column=2).number_format = "0.0%"

    kv("Credit score", result.credit_bureau.credit_score)
    kv("Average bank balance", f"=AVERAGE({trend_range('H')})")
    kv("Payment returns", m.payment_returns_count)
    if m.salary_credit_months_count is not None:
        kv("Salary credit months (of 6)", m.salary_credit_months_count)
    kv("Vintage (months)", m.vintage_months)
    kv("Unexplained large cash deposit", "Yes" if m.unexplained_cash_deposit_flag else "No")

    ws.append([])
    decision_label_row = ws.max_row + 1
    ws.append(["Decision", result.decision.value.upper()])
    fill = PatternFill(start_color=BADGE_FILL_HEX[result.decision], end_color=BADGE_FILL_HEX[result.decision], fill_type="solid")
    ws.cell(row=decision_label_row, column=1).font = _HEADER_FONT
    decision_cell = ws.cell(row=decision_label_row, column=2)
    decision_cell.fill = fill
    decision_cell.font = Font(bold=True, color="FFFFFF")
    decision_cell.alignment = Alignment(horizontal="center")

    ws.append([])
    ws.append(["Reasons"])
    ws.cell(row=ws.max_row, column=1).font = _HEADER_FONT
    fired = [r for r in result.fired_rules if r.fired]
    if fired:
        for r in fired:
            ws.append([r.rule_id, r.message])
    else:
        ws.append(["-", "No decline or refer rules fired; approved by default."])

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 60
    return ws


def generate_cashflow_excel(result: UnderwritingResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)  # remove the default blank sheet; Summary is created with index 0 below

    txn_sheet = _write_transactions_sheet(wb, result)
    trend_sheet, n_months = _write_monthly_trend_sheet(wb, result, txn_sheet.max_row - 1)
    _write_summary_sheet(wb, result, n_months)

    wb.save(output_path)
    return output_path
