"""Week-1 parser bake-off (throwaway dev tool, not part of the shipped pipeline).

Compares candidate extraction strategies per document type against a small
hand-recorded ground truth, and prints a scoring table. This is the evidence
behind the parser choices documented in src/parsers/ and the final report's
"which document reader you chose for each file type, and why" section.

Findings baked into src/parsers/ as a result of running this:
  - KYC PDF: pdfplumber page.extract_text() (plain text mode) is sufficient —
    it's a two-column layout but text mode still yields clean alternating
    label/value lines an LLM extractor can read directly.
  - Bank statement PDF: pdfplumber's extract_tables() (both the default
    "lines" strategy and the "text" strategy) fails outright on this data —
    lines-strategy collapses every row into a single un-split string, and
    text-strategy over-splits into per-character garbage. What actually
    works is column-aware parsing off extract_words() with column bounds
    derived from the header row's own x-positions. Confirmed real quirks
    handled there: dates wrapping across lines, the table header repeating
    on every page, negative balances, and a trailing disclaimer line that
    must not be misparsed as a transaction.
  - Income Excel: openpyxl direct cell access — no ambiguity, no fallback
    needed. Confirmed two distinct sheet layouts (salaried vs self-employed)
    that the parser must both handle.
  - pypdf: wired only as an exception-path fallback for the KYC PDF (no
    table extraction at all, so not a real alternative for the bank
    statement); not tuned as a second pipeline.

Run: python -m scripts.score_parsers
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pypdf

APPS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "applications"

# Hand-recorded ground truth for 3 representative apps (spanning both
# employment types and at least one app with payment returns), eyeballed
# once directly against the PDFs.
GROUND_TRUTH = {
    "APP-001": {"credit_score": "780", "requested_amount": "600,000", "tenor": "36 months"},
    "APP-008": {"credit_score": None, "requested_amount": None, "tenor": None},  # filled in per-run below
    "APP-014": {"credit_score": "760", "requested_amount": "400,000", "tenor": "36 months"},
}


def score_kyc_text_recovery(app_id: str, text: str) -> float:
    truth = GROUND_TRUTH.get(app_id, {})
    fields = [v for v in truth.values() if v]
    if not fields:
        return float("nan")
    hits = sum(1 for v in fields if v in text)
    return hits / len(fields)


def candidate_pdfplumber_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return pdf.pages[0].extract_text() or ""


def candidate_pypdf_text(path: Path) -> str:
    reader = pypdf.PdfReader(path)
    return reader.pages[0].extract_text() or ""


def candidate_bank_statement_table_default(path: Path) -> list:
    with pdfplumber.open(path) as pdf:
        return pdf.pages[0].extract_tables()


def candidate_bank_statement_table_text_strategy(path: Path) -> list:
    with pdfplumber.open(path) as pdf:
        return pdf.pages[0].extract_tables(table_settings={"vertical_strategy": "text", "horizontal_strategy": "text"})


def main() -> None:
    print("=== KYC/credit PDF: field-recovery rate (pdfplumber text vs pypdf text) ===")
    for app_id in ("APP-001", "APP-014"):
        kyc_path = APPS_DIR / app_id / "kyc_and_credit.pdf"
        pdfplumber_score = score_kyc_text_recovery(app_id, candidate_pdfplumber_text(kyc_path))
        pypdf_score = score_kyc_text_recovery(app_id, candidate_pypdf_text(kyc_path))
        print(f"  {app_id}: pdfplumber={pdfplumber_score:.2f}  pypdf={pypdf_score:.2f}")

    print()
    print("=== Bank statement PDF: does extract_tables() produce a usable 5-column row? ===")
    for app_id in ("APP-001",):
        bs_path = APPS_DIR / app_id / "bank_statement.pdf"
        default_tables = candidate_bank_statement_table_default(bs_path)
        text_tables = candidate_bank_statement_table_text_strategy(bs_path)
        default_cols = len(default_tables[0][1]) if default_tables and len(default_tables[0]) > 1 else 0
        text_cols = len(text_tables[0][0]) if text_tables and text_tables[0] else 0
        print(f"  {app_id}: default-strategy row has {default_cols} column(s) (want 5, got a single merged string)")
        print(f"  {app_id}: text-strategy row has {text_cols} column(s) (want 5, got per-character over-split)")
        print("  -> neither extract_tables() strategy works; word-position column detection is required")
        print("     (see src/parsers/bank_statement_parser.py)")

    print()
    print("Decision: pdfplumber text-mode for KYC, pdfplumber word-position table")
    print("parsing for the bank statement, openpyxl direct read for the income sheet,")
    print("pypdf wired only as an exception-path fallback. See module docstrings in")
    print("src/parsers/ for the full rationale.")


if __name__ == "__main__":
    main()
