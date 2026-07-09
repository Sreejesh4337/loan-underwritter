"""Unit tests for standalone helpers in src/graph/nodes.py that don't need a
full graph invocation."""

from __future__ import annotations

from src.graph.nodes import _check_parsed_document_identity


def _parsed(kyc_name: str, income_name: str, bank_holder_line: str) -> dict:
    return {
        "kyc": {"label_value_pairs": {"FULL NAME": kyc_name}},
        "income": {"header_fields": {"Applicant": income_name}},
        "bank_statement": {
            "header_text": f"ACCOUNT HOLDER ACCOUNT TYPE\n{bank_holder_line} Savings"
        },
    }


class TestCheckParsedDocumentIdentity:
    def test_matching_names_across_all_three_documents(self):
        parsed = _parsed("Rahul Mehta", "Rahul Mehta", "Rahul Mehta")
        assert _check_parsed_document_identity(parsed) is None

    def test_mismatched_kyc_name_is_rejected(self):
        parsed = _parsed("Rahul Mehta", "Rahul Mehta", "Someone Else")
        error = _check_parsed_document_identity(parsed)
        assert error is not None
        assert "name mismatch" in error

    def test_missing_bank_account_holder_is_not_a_false_positive(self):
        # extract_account_holder returns None when the header regex doesn't
        # match — this must not be treated as a mismatch.
        parsed = {
            "kyc": {"label_value_pairs": {"FULL NAME": "Rahul Mehta"}},
            "income": {"header_fields": {"Applicant": "Rahul Mehta"}},
            "bank_statement": {"header_text": "unrecognized header format"},
        }
        assert _check_parsed_document_identity(parsed) is None
