"""Parser for the bank statement PDF.

Confirmed by direct inspection of the sample packets: this file needs real
table-aware parsing, unlike the KYC PDF. Two concrete quirks drove this design:

1. `page.extract_tables()` (both the default "lines" strategy and a "text"
   strategy) does not cleanly split the statement into 5 columns on this
   data — the default strategy collapses each row into a single string, and
   the text strategy over-splits into per-character garbage. Column-aware
   parsing off raw word positions (`extract_words()`), with column
   boundaries derived from the header row's own x-positions rather than
   hardcoded, is what actually works.
2. Some dates wrap across two physical lines: e.g. "05 Aug" renders on one
   line, the transaction's description/amounts render ~5pt below it, and the
   bare "2025" wraps onto a third line below that. A naive line-based parser
   misaligns these into the wrong rows/columns. This parser explicitly
   reassembles such rows.
3. The 5-column table header repeats on every page of a multi-page
   statement (confirmed on page 2 of the sample data) — column boundaries
   must be (re)detected per page, not just once.

Transaction rows are parsed all the way to typed values here (not deferred to
an LLM): dates, descriptions, and debit/credit/balance amounts are
unambiguous tabular data, and running every row through an LLM call is
exactly the token waste the project brief's cost-minimization section calls
out. The bank-statement LLM extractor (`src/extractors/bank_statement_extractor.py`)
only handles the small header key/value block and classifying any
description that doesn't match a known regex category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from .base import ParserError

HEADER_LABELS = ("Date", "Description", "Debit", "Credit", "Balance")
ROW_CLUSTER_TOLERANCE = 3.0  # points; words within this vertical distance are treated as one physical line
_BARE_YEAR = re.compile(r"^\d{4}$")
_DATE_MISSING_YEAR = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}$")


@dataclass
class RawTransactionRow:
    date_text: str  # e.g. "05 Jul 2025" — parsed to a real date by the extractor/analysis layer
    description: str
    debit: float
    credit: float
    balance: float


@dataclass
class ParsedBankStatement:
    header_text: str
    transactions: list[RawTransactionRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
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


def _column_bounds(header_row: list[dict]) -> list[tuple[str, float, float]]:
    """Derive column x-boundaries from this page's header row (not hardcoded,
    so the parser adapts per document/page rather than relying on magic
    numbers that could drift between the 15 sample apps).

    Each column spans from its own header's x0 to the next column's header
    x0 (first column's low bound is -inf, last column's high bound is +inf)
    — NOT the midpoint between headers. Confirmed by inspection: Description
    is a wide free-text column whose header label ("Description") is much
    narrower than the actual text it holds (e.g. "ACH Debit - EXISTING LOAN
    EMI" extends well past the midpoint to the next header, "Debit (INR)",
    but never past that header's own x0 — Debit/Credit/Balance are narrow,
    right-aligned numeric columns whose values sit close to their column's
    own x0..next-x0 span regardless of digit count).
    """
    anchors = []
    for label in HEADER_LABELS:
        match = next((w for w in header_row if w["text"].startswith(label)), None)
        if match is None:
            raise ParserError(f"bank statement header missing expected column {label!r}")
        anchors.append((label, match["x0"]))
    anchors.sort(key=lambda a: a[1])

    bounds = []
    for i, (label, x0) in enumerate(anchors):
        lo = -1.0 if i == 0 else x0
        hi = float("inf") if i == len(anchors) - 1 else anchors[i + 1][1]
        bounds.append((label, lo, hi))
    return bounds


def _assign_columns(row: list[dict], bounds: list[tuple[str, float, float]]) -> dict[str, str]:
    cells: dict[str, list[str]] = {label: [] for label, _, _ in bounds}
    for w in sorted(row, key=lambda w: w["x0"]):
        for label, lo, hi in bounds:
            if lo <= w["x0"] < hi:
                cells[label].append(w["text"])
                break
    return {label: " ".join(tokens) for label, tokens in cells.items()}


_NUMERIC_CELL = re.compile(r"^-?[\d,]*\.?\d*$")  # balances can legitimately go negative (confirmed in sample data)


def _parse_amount(text: str) -> float:
    text = text.replace(",", "").strip()
    return float(text) if text else 0.0


def _has_body_content(cells: dict[str, str]) -> bool:
    return any(cells[c].strip() for c in ("Description", "Debit", "Credit", "Balance"))


def _looks_like_transaction_row(cells: dict[str, str]) -> bool:
    """Reject footer/disclaimer prose that happens to fall inside the table's
    column x-range (confirmed real case: the statement's closing disclaimer
    line, e.g. "This is a system-generated statement... entirely synthetic.",
    sits on its own physical line and gets word-wrapped into columns just
    like a real row). A genuine row's Debit/Credit/Balance cells are always
    numeric or blank; free text there means this isn't a transaction."""
    return all(_NUMERIC_CELL.match(cells[c].replace(" ", "")) for c in ("Debit", "Credit", "Balance"))


def _reassemble_wrapped_rows(raw_rows: list[dict[str, str]]) -> tuple[list[RawTransactionRow], list[str]]:
    """Merge date fragments split across lines back into single transaction rows.

    Confirmed pattern in the sample data: "05 Aug" on one line, the
    description/amounts on the next, then a bare "2025" on a third line.
    """
    warnings: list[str] = []
    transactions: list[RawTransactionRow] = []
    pending_date: str | None = None
    pending_row: RawTransactionRow | None = None

    for cells in raw_rows:
        date_text = cells["Date"].strip()

        if date_text and not _has_body_content(cells):
            # A date-only line: either a leading fragment ("05 Aug") awaiting its
            # body row, or a trailing year ("2025") completing an already-emitted
            # row that's still missing its year.
            if pending_row is not None and _BARE_YEAR.match(date_text):
                pending_row.date_text = f"{pending_row.date_text} {date_text}".strip()
                transactions.append(pending_row)
                pending_row = None
            else:
                pending_date = date_text
            continue

        if not _has_body_content(cells):
            continue  # blank line

        if not _looks_like_transaction_row(cells):
            warnings.append(f"skipped a non-transaction line (likely footer/disclaimer text): {cells}")
            continue

        row_date = date_text or pending_date or ""
        pending_date = None
        if not row_date:
            warnings.append(f"transaction row missing a date entirely: {cells}")

        row = RawTransactionRow(
            date_text=row_date,
            description=cells["Description"].strip(),
            debit=_parse_amount(cells["Debit"]),
            credit=_parse_amount(cells["Credit"]),
            balance=_parse_amount(cells["Balance"]),
        )

        if _DATE_MISSING_YEAR.match(row_date):
            pending_row = row  # wait for the trailing year fragment
        else:
            transactions.append(row)

    if pending_row is not None:
        warnings.append(f"transaction row never completed with a year, kept as-is: {pending_row.date_text!r}")
        transactions.append(pending_row)

    return transactions, warnings


def parse_bank_statement_pdf(path: Path) -> ParsedBankStatement:
    header_lines: list[str] = []
    raw_rows: list[dict[str, str]] = []
    bounds: list[tuple[str, float, float]] | None = None

    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise ParserError(f"{path} has no pages")
            for page in pdf.pages:
                words = page.extract_words()
                if not words:
                    continue
                for row in _cluster_rows(words):
                    if _is_header_row(row):
                        bounds = _column_bounds(row)  # header repeats on every page
                        continue
                    row_text = " ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]))
                    if bounds is None:
                        header_lines.append(row_text)
                        continue
                    raw_rows.append(_assign_columns(row, bounds))
    except ParserError:
        raise
    except Exception as exc:
        raise ParserError(f"failed to parse bank statement PDF {path}: {exc}") from exc

    if bounds is None:
        raise ParserError(f"could not locate the transaction table header in {path}")

    transactions, warnings = _reassemble_wrapped_rows(raw_rows)
    if not transactions:
        warnings.append("no transactions were parsed from the statement")

    return ParsedBankStatement(
        header_text="\n".join(header_lines).strip(),
        transactions=transactions,
        warnings=warnings,
        source_file=str(path),
    )
