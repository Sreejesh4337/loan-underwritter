"""Upload-time document-type validation.

Runs before any document is saved to the database: given the raw bytes of an
uploaded file and the document type expected for its upload slot, decides
whether the bytes actually look like that type of document. Uses the same
structural markers each parser already owns (src/parsers/*.py) via their
cheap, non-raising `sniff_*` functions rather than a full parse — this is
deliberately a heuristic fingerprint check, not validation that the document
is well-formed enough for the pipeline to consume it.
"""

from __future__ import annotations

from src.parsers.bank_statement_parser import sniff_bank_statement
from src.parsers.income_parser import sniff_income
from src.parsers.kyc_parser import KYC_SNIFF_MIN_LABEL_MATCHES, sniff_kyc
from src.schemas.underwriting import DocumentType

_DISPLAY_NAMES: dict[DocumentType, str] = {
    DocumentType.BANK_STATEMENT: "Bank Statement",
    DocumentType.KYC_AND_CREDIT: "KYC & Credit document",
    DocumentType.INCOME_DETAILS: "Income Details sheet",
}


def detect_document_type(content: bytes) -> DocumentType | None:
    """Classify `content` as one of the three known document types, or None
    if it doesn't confidently match any of them.

    Bank statement and income are checked first since their structural
    markers are near-exact (a fixed 5-column table header / a fixed sheet
    marker); KYC is checked last as a fuzzy label-count threshold so it
    can't shadow an exact match on the other two.
    """
    if sniff_bank_statement(content):
        return DocumentType.BANK_STATEMENT
    if sniff_income(content):
        return DocumentType.INCOME_DETAILS
    if sniff_kyc(content) >= KYC_SNIFF_MIN_LABEL_MATCHES:
        return DocumentType.KYC_AND_CREDIT
    return None


def validate_document(expected: DocumentType, content: bytes) -> str | None:
    """Return a user-facing error message if `content` doesn't look like
    `expected`'s document type, else None (valid)."""
    if not content:
        return f"The uploaded {_DISPLAY_NAMES[expected]} file is empty."

    detected = detect_document_type(content)
    if detected == expected:
        return None

    base = f"Invalid document. Please upload a valid {_DISPLAY_NAMES[expected]}."
    if detected is None:
        return base
    return f"{base} It looks like you uploaded a {_DISPLAY_NAMES[detected]} instead."
