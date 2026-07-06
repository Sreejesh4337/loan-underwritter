"""Unit tests for the extraction layer, run in deterministic-fallback mode
(no OPENAI_API_KEY configured in this sandbox — llm_available() is False,
so every extractor exercises its fallback path). This is still a genuine
correctness test of the fallback, which is what the pipeline actually runs
on in this environment."""

from __future__ import annotations

from pathlib import Path

from src.extractors.bank_statement_extractor import classify_unmatched_descriptions, extract_account_holder
from src.extractors.income_extractor import extract_income
from src.extractors.kyc_extractor import extract_kyc
from src.parsers.registry import parse_bank_statement, parse_income, parse_kyc
from src.schemas.underwriting import EmploymentType, TransactionCategory

APPS_DIR = Path(__file__).resolve().parents[2].parent / "docs" / "applications"


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
    def test_extracts_account_holder(self):
        doc = parse_bank_statement(APPS_DIR / "APP-001" / "bank_statement.pdf")
        holder, acct_type = extract_account_holder(doc)
        assert holder == "Rahul Mehta"
        assert acct_type == "Savings"

    def test_classifies_no_unmatched_descriptions_as_empty(self):
        classifications, usage = classify_unmatched_descriptions([])
        assert classifications == {}

    def test_fallback_classification_defaults_to_other(self):
        classifications, usage = classify_unmatched_descriptions(["Some Unknown Transaction"])
        assert classifications["Some Unknown Transaction"] == TransactionCategory.OTHER
        assert usage.model == "deterministic-fallback"
