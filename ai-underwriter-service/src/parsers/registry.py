"""Parser dispatch with the pypdf exception-path fallback.

Per the plan: pypdf is not a second tuned pipeline, it's a defensive fallback
wired as try/except around the primary pdfplumber call. It has no table
extraction, so it's only meaningful as a fallback for the KYC PDF (plain text)
— if the bank statement's primary parser fails, there's no reasonable text-only
substitute, so we surface the error for the graph's bad-input handling instead
of silently degrading numeric table data.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pypdf

from .bank_statement_parser import ParsedBankStatement, parse_bank_statement_pdf
from .base import ParserError
from .income_parser import ParsedIncomeDocument, parse_income_xlsx
from .kyc_parser import ParsedKycDocument, parse_kyc_pdf

logger = logging.getLogger(__name__)


def _pypdf_fallback_text(path: Path) -> str:
    try:
        reader = pypdf.PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ParserError(f"pypdf fallback also failed for {path}: {exc}") from exc


def parse_kyc(path: Path) -> ParsedKycDocument:
    try:
        return parse_kyc_pdf(path)
    except ParserError as exc:
        logger.warning("pdfplumber failed on KYC PDF %s (%s); falling back to pypdf", path, exc)
        text = _pypdf_fallback_text(path)
        if not text.strip():
            raise
        return ParsedKycDocument(raw_text=text, source_file=str(path))


def parse_bank_statement(path: Path) -> ParsedBankStatement:
    # No fallback here by design: pypdf can't recover a structured transaction
    # table, and a partially-wrong table is worse than a clear failure that
    # routes to the graph's handle_bad_input path.
    return parse_bank_statement_pdf(path)


def parse_income(path: Path) -> ParsedIncomeDocument:
    return parse_income_xlsx(path)
