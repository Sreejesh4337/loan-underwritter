"""Parser for the bank statement PDF.

This module only pulls raw text out of the PDF (pdfplumber). Turning that
text into structured transaction rows (dates, amounts, categories) is now
the LLM extractor's job (see `src/extractors/bank_statement_extractor.py`)
rather than position/regex-based logic here.

`sniff_bank_statement` is a cheap upload-time presence check (does the
transaction table header appear on page 1?) — it stays in this module and
stays regex/position-based since it's a validation check, not extraction.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from .base import ParserError

HEADER_LABELS = ("Date", "Description", "Debit", "Credit", "Balance")
ROW_CLUSTER_TOLERANCE = 3.0  # points; words within this vertical distance are treated as one physical line


@dataclass
class ParsedBankStatement:
    raw_text: str
    source_file: str = ""


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into physical lines by vertical position."""
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(w["top"] - rows[-1][-1]["top"]) <= ROW_CLUSTER_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
    return rows


def _is_header_row(row: list[dict]) -> bool:
    return all(any(w["text"].startswith(label) for w in row) for label in HEADER_LABELS)


def sniff_bank_statement(content: bytes) -> bool:
    """Return True iff the transaction table header row is found on the
    first page. Cheap presence check for upload-time document-type
    validation — the header repeats on every page, so checking page 1 is
    sufficient. Never raises; returns False for unreadable or non-PDF
    bytes."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if not pdf.pages:
                return False
            words = pdf.pages[0].extract_words()
            if not words:
                return False
            return any(_is_header_row(row) for row in _cluster_rows(words))
    except Exception:
        return False


def parse_bank_statement_pdf(path: Path) -> ParsedBankStatement:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise ParserError(f"{path} has no pages")
            raw_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ParserError:
        raise
    except Exception as exc:
        raise ParserError(f"failed to parse bank statement PDF {path}: {exc}") from exc

    if not raw_text.strip():
        raise ParserError(f"bank statement PDF {path} produced no extractable text")

    return ParsedBankStatement(raw_text=raw_text, source_file=str(path))
