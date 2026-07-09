"""Unit tests for upload-time document-type validation, run against the real
sample application packets in docs/applications/ — no mocking, mirrors
test_parsers.py's pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.schemas.underwriting import DocumentType
from src.validation.document_validator import detect_document_type, validate_document

APPS_DIR = Path(__file__).resolve().parents[2].parent / "docs" / "applications"
ALL_APP_IDS = sorted(p.name for p in APPS_DIR.iterdir() if p.name.startswith("APP-"))


def app_bytes(app_id: str, filename: str) -> bytes:
    return (APPS_DIR / app_id / filename).read_bytes()


class TestMatchingDocuments:
    @pytest.mark.parametrize("app_id", ALL_APP_IDS)
    def test_bank_statement_validates(self, app_id):
        content = app_bytes(app_id, "bank_statement.pdf")
        assert validate_document(DocumentType.BANK_STATEMENT, content) is None

    @pytest.mark.parametrize("app_id", ALL_APP_IDS)
    def test_kyc_validates(self, app_id):
        content = app_bytes(app_id, "kyc_and_credit.pdf")
        assert validate_document(DocumentType.KYC_AND_CREDIT, content) is None

    @pytest.mark.parametrize("app_id", ALL_APP_IDS)
    def test_income_validates(self, app_id):
        content = app_bytes(app_id, "income_details.xlsx")
        assert validate_document(DocumentType.INCOME_DETAILS, content) is None


class TestMismatchedDocuments:
    def test_kyc_uploaded_as_bank_statement_is_rejected(self):
        content = app_bytes("APP-001", "kyc_and_credit.pdf")
        message = validate_document(DocumentType.BANK_STATEMENT, content)
        assert message is not None
        assert "Bank Statement" in message
        assert "KYC" in message

    def test_bank_statement_uploaded_as_kyc_is_rejected(self):
        content = app_bytes("APP-001", "bank_statement.pdf")
        message = validate_document(DocumentType.KYC_AND_CREDIT, content)
        assert message is not None
        assert "KYC" in message
        assert "Bank Statement" in message

    def test_income_uploaded_as_bank_statement_is_rejected(self):
        content = app_bytes("APP-001", "income_details.xlsx")
        message = validate_document(DocumentType.BANK_STATEMENT, content)
        assert message is not None
        assert "Bank Statement" in message

    def test_bank_statement_uploaded_as_income_is_rejected(self):
        content = app_bytes("APP-001", "bank_statement.pdf")
        message = validate_document(DocumentType.INCOME_DETAILS, content)
        assert message is not None
        assert "Income Details" in message

    def test_income_uploaded_as_kyc_is_rejected(self):
        content = app_bytes("APP-001", "income_details.xlsx")
        message = validate_document(DocumentType.KYC_AND_CREDIT, content)
        assert message is not None
        assert "KYC" in message


class TestEdgeCases:
    @pytest.mark.parametrize(
        "expected",
        [DocumentType.BANK_STATEMENT, DocumentType.KYC_AND_CREDIT, DocumentType.INCOME_DETAILS],
    )
    def test_empty_file_is_rejected(self, expected):
        message = validate_document(expected, b"")
        assert message is not None
        assert "empty" in message.lower()

    def test_corrupted_bytes_do_not_raise(self):
        garbage = b"this is not a pdf or an xlsx file at all"
        message = validate_document(DocumentType.BANK_STATEMENT, garbage)
        assert message is not None
        assert "Bank Statement" in message

    def test_detect_document_type_returns_none_for_garbage(self):
        assert detect_document_type(b"random unrecognizable bytes") is None
