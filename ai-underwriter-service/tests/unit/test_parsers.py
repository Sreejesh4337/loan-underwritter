"""Unit tests for the raw-text parser layer, run against the real sample
application packets in docs/applications/ — no LLM calls needed, since these
parsers only pull text out of PDFs/Excel (see src/parsers/base.py); turning
that text into structured fields is the LLM extractor's job, tested in
tests/unit/test_extractors.py.
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
        assert result.raw_text.strip()

    def test_captures_transaction_table_content(self):
        result = parse_bank_statement_pdf(app_path("APP-001", "bank_statement.pdf"))
        assert "05 Aug" in result.raw_text or "05 Aug 2025" in result.raw_text

    def test_raises_on_missing_file(self):
        with pytest.raises(ParserError):
            parse_bank_statement_pdf(app_path("APP-001", "does_not_exist.pdf"))


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
