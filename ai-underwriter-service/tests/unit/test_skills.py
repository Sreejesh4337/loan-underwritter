"""Unit tests for the output-generator "skills" — no LLM involved, fast and
deterministic. Builds a hand-crafted UnderwritingResult fixture, generates
each artifact, then re-opens it to assert on required content."""

from __future__ import annotations

from datetime import date, datetime

import openpyxl
import pdfplumber
import pytest

from src.schemas.underwriting import (
    Applicant,
    CreditBureau,
    Decision,
    EmploymentType,
    FiredRule,
    FinancialMetrics,
    LoanRequest,
    RuleTier,
    RunUsage,
    Transaction,
    TransactionCategory,
    UnderwritingResult,
)
from src.skills.cashflow_generator import generate_cashflow_excel
from src.skills.memo_generator import generate_underwriting_memo


def make_result(decision: Decision = Decision.REFER) -> UnderwritingResult:
    transactions = [
        Transaction(txn_date=date(2025, 7, 5), description="Salary Credit", debit=0, credit=120000, balance=140000, category=TransactionCategory.SALARY),
        Transaction(txn_date=date(2025, 7, 7), description="EMI", debit=8000, credit=0, balance=132000, category=TransactionCategory.EMI),
        Transaction(txn_date=date(2025, 8, 5), description="Salary Credit", debit=0, credit=120000, balance=147000, category=TransactionCategory.SALARY),
        Transaction(txn_date=date(2025, 8, 7), description="EMI", debit=8000, credit=0, balance=139000, category=TransactionCategory.EMI),
    ]
    fired_rules = [
        FiredRule(rule_id="R3_PAYMENT_RETURNS", tier=RuleTier.REFER, message="Exactly 2 payment returns were found.")
    ]
    return UnderwritingResult(
        application_id="APP-TEST",
        run_id="run_1",
        thread_id="APP-TEST:run_1",
        applicant=Applicant(
            applicant_id="APP-TEST",
            full_name="Test Applicant",
            employment_type=EmploymentType.SALARIED,
            employer_or_business="Acme Corp",
            city="Bengaluru",
            state="Karnataka",
        ),
        loan_request=LoanRequest(product="Unsecured Personal Loan", requested_amount=500000, tenor_months=36, indicative_rate_pct=14.0),
        credit_bureau=CreditBureau(credit_score=690, active_loans=1, delinquencies_12m=0, enquiries_6m=2),
        metrics=FinancialMetrics(
            net_monthly_income=120000,
            net_monthly_income_source="income_sheet",
            existing_emis=8000,
            proposed_emi=17000,
            foir_pct=20.8,
            avg_bank_balance=140000,
            payment_returns_count=2,
            salary_credit_months_count=6,
            vintage_months=24,
            unexplained_cash_deposit_flag=False,
        ),
        transactions=transactions,
        decision=decision,
        fired_rules=fired_rules if decision != Decision.APPROVE else [],
        rationale_text="Two payment returns were observed; recommend manual review.",
        advisory_notes=["Applicant has one active existing loan."],
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
        usage=RunUsage(total_input_tokens=500, total_output_tokens=200, total_cost_usd=0.01),
    )


class TestMemoGenerator:
    def test_generates_pdf_with_required_sections(self, tmp_path):
        result = make_result()
        path = generate_underwriting_memo(result, tmp_path / "memo.pdf")

        assert path.exists()
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        assert "Test Applicant" in text
        assert "REFER" in text
        assert "R3_PAYMENT_RETURNS" in text
        assert "AI-generated recommendation" in text
        assert "500,000" in text  # requested amount, formatted

    def test_approve_decision_has_no_reasons(self, tmp_path):
        result = make_result(decision=Decision.APPROVE)
        path = generate_underwriting_memo(result, tmp_path / "memo.pdf")
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "APPROVE" in text
        assert "approved by default" in text


class TestCashflowGenerator:
    def test_generates_workbook_with_expected_sheets(self, tmp_path):
        result = make_result()
        path = generate_cashflow_excel(result, tmp_path / "cashflow.xlsx")

        assert path.exists()
        wb = openpyxl.load_workbook(path)
        assert set(wb.sheetnames) == {"Summary", "Transactions", "Monthly Trend"}

    def test_summary_ratio_cells_are_formulas_not_literals(self, tmp_path):
        result = make_result()
        path = generate_cashflow_excel(result, tmp_path / "cashflow.xlsx")
        wb = openpyxl.load_workbook(path)
        ws = wb["Summary"]

        formula_cells = [cell.value for row in ws.iter_rows() for cell in row if isinstance(cell.value, str) and cell.value.startswith("=")]
        assert any("AVERAGE" in f for f in formula_cells)
        assert any(f.count("B") >= 1 and "/" in f for f in formula_cells)  # the FOIR formula

    def test_transactions_sheet_has_one_row_per_transaction(self, tmp_path):
        result = make_result()
        path = generate_cashflow_excel(result, tmp_path / "cashflow.xlsx")
        wb = openpyxl.load_workbook(path)
        ws = wb["Transactions"]
        assert ws.max_row == len(result.transactions) + 1  # +1 header

    def test_monthly_trend_formulas_reference_transactions_sheet(self, tmp_path):
        result = make_result()
        path = generate_cashflow_excel(result, tmp_path / "cashflow.xlsx")
        wb = openpyxl.load_workbook(path)
        ws = wb["Monthly Trend"]
        row2_values = [ws.cell(row=2, column=c).value for c in range(4, 9)]
        assert all(isinstance(v, str) and v.startswith("=") and "Transactions!" in v for v in row2_values)
