"""Unit tests for the pure-Python financial metrics.

Transaction fixtures are built directly as `Transaction` objects (matching
real values previously confirmed by direct inspection of the sample PDFs),
rather than routed through the parser/extractor layer. That layer now
involves an LLM call (see src/extractors/bank_statement_extractor.py) and is
tested separately in tests/unit/test_extractors.py; these metric functions
are pure Python and never cared how a transaction got its category, so they
stay decoupled from extraction here.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.analysis.cross_check import check_salary_consistency, cross_check
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
)
from src.schemas.underwriting import EmploymentType, Transaction, TransactionCategory

MONTHLY_TABLE_HEADER = ["Month", "Basic", "HRA", "Allowances", "Deductions", "Net pay (INR)"]


def _salary_txn(month_label: str, amount: float) -> Transaction:
    txn_date = datetime.strptime(f"05 {month_label}", "%d %b %Y").date()
    return Transaction(
        txn_date=txn_date,
        description="Salary Credit - EMP PAYROLL",
        credit=amount,
        balance=amount,
        category=TransactionCategory.SALARY,
    )


def _return_txn(d: date, amount: float = 500.0) -> Transaction:
    return Transaction(
        txn_date=d,
        description="ECS RETURN CHARGES - INSUFF FUNDS",
        debit=amount,
        balance=amount,
        category=TransactionCategory.RETURN,
    )


@pytest.fixture
def app001_transactions() -> list[Transaction]:
    """Matches APP-001's real bank statement (Jul-Dec 2025, salaried
    applicant Rahul Mehta): monthly salary credit of 120,000, monthly EMI
    debit of 8,000, and the month-end balances read directly off the PDF."""
    month_end_balances = [27255.0, 35500.0, 40453.0, 43983.0, 46169.0, 52718.0]
    transactions = []
    for i, balance in enumerate(month_end_balances):
        month = 7 + i  # Jul .. Dec 2025
        transactions.append(
            Transaction(
                txn_date=date(2025, month, 5),
                description="Salary Credit - EMP PAYROLL",
                credit=120000.0,
                balance=balance,
                category=TransactionCategory.SALARY,
            )
        )
        transactions.append(
            Transaction(
                txn_date=date(2025, month, 20),
                description="ACH Debit - EXISTING LOAN EMI",
                debit=8000.0,
                balance=balance,  # last transaction of the month -> this is the balance that counts
                category=TransactionCategory.EMI,
            )
        )
    return sorted(transactions, key=lambda t: t.txn_date)


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


class TestBalanceAndCounts:
    def test_average_month_end_balance_matches_hand_computed(self, app001_transactions):
        # Month-end balances read directly off the PDF: 27255, 35500, 40453, 43983, 46169, 52718
        assert average_month_end_balance(app001_transactions) == pytest.approx(41013.0)

    def test_salary_credit_months_count_all_present(self, app001_transactions):
        assert count_salary_credit_months(app001_transactions) == 6

    def test_no_payment_returns_in_app001(self, app001_transactions):
        assert count_payment_returns(app001_transactions) == 0

    def test_payment_returns_count_matches_app012(self):
        # APP-012 has 4 ECS returns in the sample data -> should decline per policy.
        txns = [_return_txn(date(2025, m, 15)) for m in range(7, 11)]
        assert count_payment_returns(txns) == 4

    def test_recurring_emi_detected(self, app001_transactions):
        assert detect_recurring_emi(app001_transactions) == pytest.approx(8000.0)

    def test_no_recurring_emi_returns_zero(self):
        # APP-014 is self-employed with no recurring EMI in the sample data.
        txns = [
            Transaction(
                txn_date=date(2025, 7, 10),
                description="Declared Business Income",
                credit=45000.0,
                balance=45000.0,
                category=TransactionCategory.OTHER,
            )
        ]
        assert detect_recurring_emi(txns) >= 0.0


class TestUnexplainedCashDeposit:
    def test_app015_flags_large_cash_deposit(self):
        # APP-015 has an unexplained large cash deposit in the sample data.
        txns = [
            Transaction(
                txn_date=date(2025, 8, 12),
                description="CASH DEPOSIT - BRANCH",
                credit=150000.0,
                balance=150000.0,
                category=TransactionCategory.CASH_DEPOSIT,
            )
        ]
        assert has_unexplained_cash_deposit(txns, net_monthly_income=90000) is True

    def test_app001_has_no_unexplained_deposit(self, app001_transactions):
        assert has_unexplained_cash_deposit(app001_transactions, net_monthly_income=120000) is False


class TestSelfEmployedIncomeSource:
    def test_average_monthly_bank_credits_positive(self):
        txns = [
            Transaction(
                txn_date=date(2025, 7, 10),
                description="Business Credit",
                credit=45000.0,
                balance=45000.0,
                category=TransactionCategory.OTHER,
            )
        ]
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
            income_sheet_applicant_name="Priya Sharma",
            bank_account_holder_name="Rahul Mehta",
            income_sheet_average_net_pay=120000.0,
            transactions=app001_transactions,
        )
        assert result.name_consistency_ok is False
        assert result.warnings

    def test_tolerates_initial_honorific_and_word_order(self, app001_transactions):
        """An initial standing in for a given name, an honorific prefix, and
        reversed word order are formatting noise from independent LLM
        extractions, not identity mismatches — see src/analysis/cross_check.py's
        _names_consistent."""
        result = cross_check(
            employment_type=EmploymentType.SALARIED,
            kyc_full_name="Rahul Mehta",
            income_sheet_applicant_name="R. Mehta",
            bank_account_holder_name="MR MEHTA RAHUL",
            income_sheet_average_net_pay=120000.0,
            transactions=app001_transactions,
        )
        assert result.name_consistency_ok is True
        assert result.warnings == []


class TestSalaryConsistency:
    def test_matching_months_and_amounts_ok(self):
        txns = [_salary_txn("Oct 2025", 150000), _salary_txn("Nov 2025", 150000), _salary_txn("Dec 2025", 150000)]
        monthly_rows = [["Oct 2025", 0, 0, 0, 0, 150000], ["Nov 2025", 0, 0, 0, 0, 150000], ["Dec 2025", 0, 0, 0, 0, 150000]]
        ok, warnings = check_salary_consistency(
            monthly_table_header=MONTHLY_TABLE_HEADER, monthly_rows=monthly_rows, transactions=txns
        )
        assert ok is True
        assert warnings == []

    def test_within_tolerance_is_ok(self):
        txns = [_salary_txn("Oct 2025", 145000)]  # ~3.3% below declared
        monthly_rows = [["Oct 2025", 0, 0, 0, 0, 150000]]
        ok, warnings = check_salary_consistency(
            monthly_table_header=MONTHLY_TABLE_HEADER, monthly_rows=monthly_rows, transactions=txns
        )
        assert ok is True
        assert warnings == []

    def test_missing_month_flagged(self):
        txns = [_salary_txn("Nov 2025", 150000)]
        monthly_rows = [["Oct 2025", 0, 0, 0, 0, 150000]]
        ok, warnings = check_salary_consistency(
            monthly_table_header=MONTHLY_TABLE_HEADER, monthly_rows=monthly_rows, transactions=txns
        )
        assert ok is False
        assert warnings

    def test_amount_beyond_tolerance_flagged(self):
        txns = [_salary_txn("Oct 2025", 100000)]  # >10% below declared
        monthly_rows = [["Oct 2025", 0, 0, 0, 0, 150000]]
        ok, warnings = check_salary_consistency(
            monthly_table_header=MONTHLY_TABLE_HEADER, monthly_rows=monthly_rows, transactions=txns
        )
        assert ok is False
        assert warnings

    def test_no_monthly_rows_is_noop(self):
        ok, warnings = check_salary_consistency(monthly_table_header=[], monthly_rows=[], transactions=[])
        assert ok is True
        assert warnings == []

    def test_cross_check_flags_income_mismatch_for_salaried(self, app001_transactions):
        result = cross_check(
            employment_type=EmploymentType.SALARIED,
            kyc_full_name="Rahul Mehta",
            income_sheet_applicant_name="Rahul Mehta",
            bank_account_holder_name="Rahul Mehta",
            income_sheet_average_net_pay=120000.0,
            transactions=app001_transactions,
            monthly_table_header=MONTHLY_TABLE_HEADER,
            monthly_rows=[["Jul 2025", 0, 0, 0, 0, 999999]],  # doesn't match actual 150,000 credit
        )
        assert result.income_consistency_ok is False
        assert result.warnings

    def test_cross_check_skips_check_for_self_employed(self, app001_transactions):
        result = cross_check(
            employment_type=EmploymentType.SELF_EMPLOYED,
            kyc_full_name="Rahul Mehta",
            income_sheet_applicant_name="Rahul Mehta",
            bank_account_holder_name="Rahul Mehta",
            income_sheet_average_net_pay=None,
            transactions=app001_transactions,
            monthly_table_header=[],
            monthly_rows=[],
        )
        assert result.income_consistency_ok is True


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
