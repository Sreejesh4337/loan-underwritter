"""Parser for the KYC & Credit Summary PDF.

This module only pulls raw text out of the PDF (pdfplumber's layout-aware
`extract_text()`, which respects horizontal position when joining words on a
line). Turning that text into typed fields is the LLM extractor's job (see
`src/extractors/kyc_extractor.py`) rather than position-based label/value
splitting here.

`sniff_kyc` is a cheap upload-time presence check — it stays regex/text-match
based since it's a validation check, not extraction.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from .base import ParserError

# Labels used only for the upload-time "does this look like a KYC doc" sniff
# check — matched verbatim against page-1 text.
KNOWN_LABELS = (
    "FULL NAME",
    "DATE OF BIRTH",
    "PAN (MASKED)",
    "MOBILE (MASKED)",
    "EMPLOYMENT TYPE",
    "EMPLOYER / BUSINESS",
    "ADDRESS",
    "CITY / STATE",
    "CREDIT SCORE",
    "ACTIVE LOANS",
    "PAST 12M DELINQUENCIES",
    "ENQUIRIES (6M)",
    "PRODUCT",
    "REQUESTED AMOUNT",
    "TENOR",
    "INDICATIVE RATE",
)

# Threshold for the upload-time "does this look like a KYC doc" sniff check
# (out of len(KNOWN_LABELS) == 16). KYC uses a fraction-matched threshold
# rather than an exact structural marker (unlike bank statement/income)
# because page-1 text extraction can partially succeed on odd inputs.
KYC_SNIFF_MIN_LABEL_MATCHES = 6


def sniff_kyc(content: bytes) -> int:
    """Return how many KNOWN_LABELS appear verbatim in the first page's raw
    text. Cheap presence check for upload-time document-type validation. Never
    raises; returns 0 for unreadable or non-PDF bytes."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if not pdf.pages:
                return 0
            text = pdf.pages[0].extract_text() or ""
    except Exception:
        return 0
    return sum(1 for label in KNOWN_LABELS if label in text)


@dataclass
class ParsedKycDocument:
    raw_text: str
    source_file: str = ""


def parse_kyc_pdf(path: Path) -> ParsedKycDocument:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise ParserError(f"{path} has no pages")
            text = pdf.pages[0].extract_text() or ""
    except ParserError:
        raise
    except Exception as exc:  # pdfplumber/pdfminer can raise several exception types
        raise ParserError(f"failed to parse KYC PDF {path}: {exc}") from exc

    if not text.strip():
        raise ParserError(f"KYC PDF {path} produced no extractable text")

    return ParsedKycDocument(raw_text=text, source_file=str(path))
