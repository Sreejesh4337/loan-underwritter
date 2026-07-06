"""Unit tests for the deterministic parser layer, run against the real sample
application packets in docs/applications/ — no LLM calls, no mocking needed
since these parsers are pure functions over real files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.parsers.base import ParserError
from src.parsers.bank_statement_parser import parse_bank_statement_pdf
from src.parsers.income_parser import parse_income_xlsx
from src.parsers.kyc_parser import parse_kyc_pdf
from src.parsers.registry import parse_bank_statement, parse_kyc

APPS_DIR = Path(__file__).resolve().parents[2].parent / "docs" / "applications"
ALL_APP_IDS = sorted(p.name for p in APPS_DIR.iterdir() if p.name.startswith("APP-"))


def app_path(app_id: str, filename: str) -> Path:
    return APPS_DIR / app_id / filename


class TestKycParser:
    def test_extracts_known_fields(self):
        doc = parse_kyc_pdf(app_path("APP-001", "kyc_and_credit.pdf"))
        assert "Rahul Mehta" in doc.raw_text
        assert "780" in doc.raw_text  # credit score
        assert "INR 600,000" in doc.raw_text

    def test_raises_on_missing_file(self):
        with pytest.raises(ParserError):
            parse_kyc_pdf(app_path("APP-001", "does_not_exist.pdf"))

    def test_registry_falls_back_gracefully(self):
        # The registry wrapper should behave identically to the raw parser
        # on a well-formed file (no fallback needed).
        doc = parse_kyc(app_path("APP-001", "kyc_and_credit.pdf"))
        assert "Rahul Mehta" in doc.raw_text


class TestBankStatementParser:
    @pytest.mark.parametrize("app_id", ALL_APP_IDS)
    def test_parses_every_sample_app_without_error(self, app_id):
        result = parse_bank_statement(app_path(app_id, "bank_statement.pdf"))
        assert len(result.transactions) > 0
        # The only expected warning across the fixed sample set is the
        # harmless trailing disclaimer line; anything else is a real bug.
        for w in result.warnings:
            assert "disclaimer" in w, f"unexpected warning for {app_id}: {w}"

    def test_reassembles_dates_wrapped_across_lines(self):
        # Confirmed real quirk: "05 Aug" / body / "2025" span three physical lines.
        result = parse_bank_statement_pdf(app_path("APP-001", "bank_statement.pdf"))
        dates = [t.date_text for t in result.transactions]
        assert "05 Aug 2025" in dates

    def test_preserves_negative_balances(self):
        # Confirmed real quirk: heavy-spending months can drive the balance
        # negative; those rows must not be mistaken for footer/disclaimer text.
        result = parse_bank_statement_pdf(app_path("APP-004", "bank_statement.pdf"))
        assert any(t.balance < 0 for t in result.transactions)

    def test_captures_payment_return_transactions(self):
        # APP-012 has 4 ECS returns in the sample data -> should decline per policy.
        result = parse_bank_statement_pdf(app_path("APP-012", "bank_statement.pdf"))
        returns = [t for t in result.transactions if "RETURN" in t.description.upper()]
        assert len(returns) == 4

    def test_captures_cash_deposit_transaction(self):
        # APP-015 has an unexplained large cash deposit in the sample data.
        result = parse_bank_statement_pdf(app_path("APP-015", "bank_statement.pdf"))
        deposits = [t for t in result.transactions if "DEPOSIT" in t.description.upper()]
        assert len(deposits) == 1
        assert deposits[0].credit == pytest.approx(150000.0)

    def test_ignores_trailing_disclaimer_line(self):
        result = parse_bank_statement_pdf(app_path("APP-001", "bank_statement.pdf"))
        assert not any("synthetic" in t.description.lower() for t in result.transactions)


class TestIncomeParser:
    def test_parses_salaried_layout(self):
        doc = parse_income_xlsx(app_path("APP-001", "income_details.xlsx"))
        assert doc.header_fields["Employment type"] == "Salaried"
        assert doc.average_net_pay == pytest.approx(120000.0)
        assert len(doc.monthly_rows) == 3

    def test_parses_self_employed_layout(self):
        doc = parse_income_xlsx(app_path("APP-014", "income_details.xlsx"))
        assert doc.header_fields["Employment type"] == "Self-employed"
        assert doc.average_net_pay is None
        assert doc.business_items["Avg monthly bank credits (INR)"] == "108968"

    @pytest.mark.parametrize("app_id", ALL_APP_IDS)
    def test_parses_every_sample_app_without_error(self, app_id):
        doc = parse_income_xlsx(app_path(app_id, "income_details.xlsx"))
        assert doc.header_fields.get("Employment type") in {"Salaried", "Self-employed"}
