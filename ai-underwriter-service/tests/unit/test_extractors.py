"""Unit tests for the extraction layer.

The bank statement extractor tests below call the real LLM (there is no
deterministic fallback for extract_bank_statement) and explicitly restore
OPENAI_API_KEY from .env via `_enable_live_llm`, since conftest.py's autouse
fixture strips it for the rest of the suite.

KYC/income extractor tests predate that change and are unaffected by it."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values

from src.extractors.bank_statement_extractor import extract_bank_statement
from src.extractors.income_extractor import extract_income
from src.extractors.kyc_extractor import extract_kyc
from src.llm.models import get_cheap_model
from src.parsers.registry import parse_bank_statement, parse_income, parse_kyc
from src.schemas.underwriting import EmploymentType, TransactionCategory

APPS_DIR = Path(__file__).resolve().parents[2].parent / "docs" / "applications"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _enable_live_llm(monkeypatch) -> None:
    api_key = dotenv_values(ENV_PATH).get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set in .env; skipping live LLM test")
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    get_cheap_model.cache_clear()


class TestKycExtractor:
    def test_extracts_all_fields_for_salaried_applicant(self):
        doc = parse_kyc(APPS_DIR / "APP-001" / "kyc_and_credit.pdf")
        applicant, loan_request, credit_bureau, usage = extract_kyc(doc, "APP-001")

        assert applicant.applicant_id == "APP-001"
        assert applicant.full_name == "Rahul Mehta"
        assert applicant.employment_type == EmploymentType.SALARIED
        assert applicant.city == "Bengaluru"
        assert applicant.state == "Karnataka"
        assert loan_request.requested_amount == 600000.0
        assert loan_request.tenor_months == 36
        assert loan_request.indicative_rate_pct == 14.0
        assert credit_bureau.credit_score == 780
        assert usage.model == "deterministic-fallback"

    def test_extracts_self_employed_applicant(self):
        doc = parse_kyc(APPS_DIR / "APP-014" / "kyc_and_credit.pdf")
        applicant, _, credit_bureau, _ = extract_kyc(doc, "APP-014")
        assert applicant.employment_type == EmploymentType.SELF_EMPLOYED
        assert credit_bureau.credit_score == 760


class TestIncomeExtractor:
    def test_extracts_salaried_income(self):
        doc = parse_income(APPS_DIR / "APP-001" / "income_details.xlsx")
        income, usage = extract_income(doc)
        assert income.employment_type == EmploymentType.SALARIED
        assert income.average_net_pay == 120000.0
        assert income.vintage_months == 48

    def test_extracts_self_employed_vintage_without_average_net_pay(self):
        doc = parse_income(APPS_DIR / "APP-014" / "income_details.xlsx")
        income, usage = extract_income(doc)
        assert income.employment_type == EmploymentType.SELF_EMPLOYED
        assert income.average_net_pay is None
        assert income.vintage_months == 40


class TestBankStatementExtractor:
    def test_extracts_account_holder_and_transactions(self, monkeypatch):
        _enable_live_llm(monkeypatch)
        doc = parse_bank_statement(APPS_DIR / "APP-001" / "bank_statement.pdf")
        holder, acct_type, transactions, usage = extract_bank_statement(doc)
        assert holder == "Rahul Mehta"
        assert acct_type == "Savings"
        assert len(transactions) > 0
        assert any(t.category == TransactionCategory.SALARY for t in transactions)

    def test_captures_payment_return_transactions(self, monkeypatch):
        _enable_live_llm(monkeypatch)
        doc = parse_bank_statement(APPS_DIR / "APP-012" / "bank_statement.pdf")
        _, _, transactions, _ = extract_bank_statement(doc)
        returns = [t for t in transactions if t.category == TransactionCategory.RETURN]
        assert len(returns) == 4

    def test_captures_cash_deposit_transaction(self, monkeypatch):
        _enable_live_llm(monkeypatch)
        doc = parse_bank_statement(APPS_DIR / "APP-015" / "bank_statement.pdf")
        _, _, transactions, _ = extract_bank_statement(doc)
        deposits = [t for t in transactions if t.category == TransactionCategory.CASH_DEPOSIT]
        assert len(deposits) == 1
        assert deposits[0].credit == pytest.approx(150000.0)
