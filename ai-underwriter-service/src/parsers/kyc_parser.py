"""Parser for the KYC & Credit Summary PDF.

Confirmed layout (by direct inspection of the sample packets): a clean
two-column key/value page. `pdfplumber`'s layout-aware `extract_text()`
already resolves it into alternating "LABEL LABEL" / "value value" lines
(pdfplumber's text mode, unlike PyPDF's older extractor, respects horizontal
position when joining words on a line). That raw text is what the LLM
extractor reads directly.

This parser additionally recovers a clean `label -> value` dict using the
same word-position column-detection technique as the bank statement parser
(left column x0 ~68, right column x0 ~297.6, confirmed identical across the
sample apps): each known label's value is whichever line immediately follows
it in the same column. This is genuinely just "reading the document" — no
language understanding is needed since the layout is a fixed, unambiguous
grid — and it's what powers the deterministic fallback extraction path used
when no LLM is configured (see src/extractors/kyc_extractor.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .base import ParserError

# Every label on the page, in the order they appear. Matched by exact text
# after joining a line's words with single spaces.
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
_COLUMN_SPLIT_X = 200.0  # left column x0 ~68, right column x0 ~297.6 (confirmed fixed across all sample apps)
_ROW_CLUSTER_TOLERANCE = 3.0


@dataclass
class ParsedKycDocument:
    raw_text: str
    label_value_pairs: dict[str, str] = field(default_factory=dict)
    source_file: str = ""


def _extract_label_value_pairs(words: list[dict]) -> dict[str, str]:
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(w["top"] - rows[-1][-1]["top"]) <= _ROW_CLUSTER_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])

    lines: list[tuple[str, str]] = []
    for row in rows:
        left = " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]) if w["x0"] < _COLUMN_SPLIT_X)
        right = " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]) if w["x0"] >= _COLUMN_SPLIT_X)
        lines.append((left, right))

    pairs: dict[str, str] = {}
    pending_left: str | None = None
    pending_right: str | None = None
    for left, right in lines:
        if left in KNOWN_LABELS:
            pending_left = left
        elif pending_left is not None:
            pairs[pending_left] = left
            pending_left = None
        if right in KNOWN_LABELS:
            pending_right = right
        elif pending_right is not None:
            pairs[pending_right] = right
            pending_right = None
    return pairs


def parse_kyc_pdf(path: Path) -> ParsedKycDocument:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise ParserError(f"{path} has no pages")
            page = pdf.pages[0]
            text = page.extract_text() or ""
            label_value_pairs = _extract_label_value_pairs(page.extract_words())
    except ParserError:
        raise
    except Exception as exc:  # pdfplumber/pdfminer can raise several exception types
        raise ParserError(f"failed to parse KYC PDF {path}: {exc}") from exc

    if not text.strip():
        raise ParserError(f"KYC PDF {path} produced no extractable text")

    return ParsedKycDocument(raw_text=text, label_value_pairs=label_value_pairs, source_file=str(path))
