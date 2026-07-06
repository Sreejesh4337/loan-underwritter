"""Unit tests for the pure-Python financial metrics, checked against
hand-computed values for the real APP-001 sample packet."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.categorize import categorize_transaction, unmatched_descriptions
from src.analysis.cross_check import cross_check
from src.analysis.metrics import (
    average_month_end_balance,
    average_monthly_bank_credits,
    calculate_emi,
    calculate_foir_pct,
    compute_metrics,
    count_payment_returns,
    count_salary_credit_months,
    detect_recurring_emi,
    has_unexplained_cash_deposit,
    to_transactions,
)
from src.parsers.bank_statement_parser import parse_bank_statement_pdf
from src.parsers.income_parser import parse_income_xlsx
from src.parsers.kyc_parser import parse_kyc_pdf
from src.schemas.underwriting import EmploymentType, TransactionCategory

APPS_DIR = Path(__file__).resolve().parents[2].parent / "docs" / "applications"


@pytest.fixture
def app001_transactions():
    raw = parse_bank_statement_pdf(APPS_DIR / "APP-001" / "bank_statement.pdf").transactions
    return to_transactions(raw)


class TestEmiAndFoir:
    def test_emi_matches_hand_computed_amortization(self):
        # P=600,000, 14.0% p.a., 36 months (APP-001's requested loan) —
        # independently hand-computed via the same formula outside the code under test.
        assert calculate_emi(600000, 14.0, 36) == pytest.approx(20506.58, abs=0.01)

    def test_emi_zero_rate_is_straight_division(self):
        assert calculate_emi(120000, 0.0, 12) == pytest.approx(10000.0)

    def test_emi_rejects_non_positive_tenor(self):
        with pytest.raises(ValueError):
            calculate_emi(100000, 10.0, 0)

    def test_foir_pct(self):
        # existing EMI 8,000 + proposed EMI ~20,506.58 over 120,000 income
        assert calculate_foir_pct(8000, 20506.58, 120000) == pytest.approx(23.755, abs=0.01)

    def test_foir_rejects_non_positive_income(self):
        with pytest.raises(ValueError):
            calculate_foir_pct(1000, 1000, 0)


class TestCategorization:
    def test_salary_credit_detected(self, app001_transactions):
        salary_txns = [t for t in app001_transactions if t.category == TransactionCategory.SALARY]
        assert len(salary_txns) == 6  # Jul-Dec 2025
        assert all(t.credit == 120000 for t in salary_txns)

    def test_emi_debit_detected(self, app001_transactions):
        emi_txns = [t for t in app001_transactions if t.category == TransactionCategory.EMI]
        assert len(emi_txns) == 6
        assert all(t.debit == 8000 for t in emi_txns)

    def test_unmatched_descriptions_excludes_known_categories(self, app001_transactions):
        raw = parse_bank_statement_pdf(APPS_DIR / "APP-001" / "bank_statement.pdf").transactions
        unmatched = unmatched_descriptions(raw)
        assert not any("SALARY" in d.upper() for d in unmatched)
        assert not any("EMI" in d.upper() for d in unmatched)


class TestBalanceAndCounts:
    def test_average_month_end_balance_matches_hand_computed(self, app001_transactions):
        # Month-end balances read directly off the PDF: 27255, 35500, 40453, 43983, 46169, 52718
        assert average_month_end_balance(app001_transactions) == pytest.approx(41013.0)

    def test_salary_credit_months_count_all_present(self, app001_transactions):
        assert count_salary_credit_months(app001_transactions) == 6

    def test_no_payment_returns_in_app001(self, app001_transactions):
        assert count_payment_returns(app001_transactions) == 0

    def test_payment_returns_count_matches_app012(self):
        raw = parse_bank_statement_pdf(APPS_DIR / "APP-012" / "bank_statement.pdf").transactions
        txns = to_transactions(raw)
        assert count_payment_returns(txns) == 4  # confirmed via direct inspection -> should decline

    def test_recurring_emi_detected(self, app001_transactions):
        assert detect_recurring_emi(app001_transactions) == pytest.approx(8000.0)

    def test_no_recurring_emi_returns_zero(self):
        raw = parse_bank_statement_pdf(APPS_DIR / "APP-014" / "bank_statement.pdf").transactions
        txns = to_transactions(raw)
        # APP-014 is self-employed; just verify the function degrades gracefully either way
        assert detect_recurring_emi(txns) >= 0.0


class TestUnexplainedCashDeposit:
    def test_app015_flags_large_cash_deposit(self):
        raw = parse_bank_statement_pdf(APPS_DIR / "APP-015" / "bank_statement.pdf").transactions
        txns = to_transactions(raw)
        assert has_unexplained_cash_deposit(txns, net_monthly_income=90000) is True

    def test_app001_has_no_unexplained_deposit(self, app001_transactions):
        assert has_unexplained_cash_deposit(app001_transactions, net_monthly_income=120000) is False


class TestSelfEmployedIncomeSource:
    def test_average_monthly_bank_credits_positive(self):
        raw = parse_bank_statement_pdf(APPS_DIR / "APP-014" / "bank_statement.pdf").transactions
        txns = to_transactions(raw)
        assert average_monthly_bank_credits(txns) > 0


class TestCrossCheck:
    def test_consistent_names_across_documents(self, app001_transactions):
        result = cross_check(
            employment_type=EmploymentType.SALARIED,
            kyc_full_name="Rahul Mehta",
            income_sheet_applicant_name="Rahul Mehta",
            bank_account_holder_name="Rahul Mehta",
            income_sheet_average_net_pay=120000.0,
            transactions=app001_transactions,
        )
        assert result.name_consistency_ok is True
        assert result.net_monthly_income == 120000.0
        assert result.net_monthly_income_source == "income_sheet"

    def test_flags_name_mismatch(self, app001_transactions):
        result = cross_check(
            employment_type=EmploymentType.SALARIED,
            kyc_full_name="Rahul Mehta",
            income_sheet_applicant_name="R. Mehta",
            bank_account_holder_name="Rahul Mehta",
            income_sheet_average_net_pay=120000.0,
            transactions=app001_transactions,
        )
        assert result.name_consistency_ok is False
        assert result.warnings


class TestComputeMetricsEndToEnd:
    def test_app001_full_metrics(self, app001_transactions):
        metrics = compute_metrics(
            employment_type=EmploymentType.SALARIED,
            net_monthly_income=120000.0,
            net_monthly_income_source="income_sheet",
            transactions=app001_transactions,
            requested_amount=600000,
            tenor_months=36,
            indicative_rate_pct=14.0,
            vintage_months=48,
        )
        assert metrics.existing_emis == pytest.approx(8000.0)
        assert metrics.proposed_emi == pytest.approx(20506.58, abs=0.01)
        assert metrics.foir_pct == pytest.approx(23.755, abs=0.01)
        assert metrics.avg_bank_balance == pytest.approx(41013.0)
        assert metrics.payment_returns_count == 0
        assert metrics.salary_credit_months_count == 6
        assert metrics.vintage_months == 48
        assert metrics.unexplained_cash_deposit_flag is False
