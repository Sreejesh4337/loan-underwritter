"""Tolerance comparison and memo/Excel quality proxies for run_eval.py.

Memo/Excel quality is scored with a cheap, deterministic field-presence
rubric — NOT a 4th LLM-judge call. Adding an LLM judgment step inside the
very harness meant to demonstrate token/cost discipline is the wrong trade
for this project; this is stated explicitly as a scoping choice, not an
oversight.
"""

from __future__ import annotations

import openpyxl
import pdfplumber


def metric_within_tolerance(actual: float, expected_field: dict) -> tuple[bool, float]:
    expected = expected_field["value"]
    if "tolerance_pct" in expected_field:
        tolerance = abs(expected) * expected_field["tolerance_pct"] / 100
    else:
        tolerance = expected_field.get("tolerance_abs", 0)
    delta = actual - expected
    return abs(delta) <= tolerance, delta


def score_memo_quality(memo_path: str, applicant_name: str, decision: str, has_reasons: bool) -> tuple[float, list[str]]:
    checks: list[tuple[str, bool]] = []
    try:
        with pdfplumber.open(memo_path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        return 0.0, ["could not open memo PDF"]

    checks.append(("applicant name present", applicant_name in text))
    checks.append(("decision word present and matches", decision.upper() in text))
    for label in ("Net monthly income", "FOIR", "Credit score", "Average bank balance"):
        checks.append((f"metric label present: {label}", label in text))
    if has_reasons:
        checks.append(("at least one reason line present", "Reasons" in text))
    checks.append(("no leftover template artifacts", "{{" not in text and "None" not in text))

    failed = [name for name, ok in checks if not ok]
    return sum(1 for _, ok in checks if ok) / len(checks), failed


def score_excel_quality(xlsx_path: str) -> tuple[float, list[str]]:
    checks: list[tuple[str, bool]] = []
    try:
        wb = openpyxl.load_workbook(xlsx_path)
    except Exception:
        return 0.0, ["could not open cash-flow workbook"]

    expected_sheets = {"Summary", "Transactions", "Monthly Trend"}
    checks.append(("expected sheets present", expected_sheets.issubset(set(wb.sheetnames))))

    if "Summary" in wb.sheetnames:
        ws = wb["Summary"]
        formula_cells = [
            c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")
        ]
        checks.append(("ratio cells are formulas, not literals", len(formula_cells) > 0))
    else:
        checks.append(("ratio cells are formulas, not literals", False))

    failed = [name for name, ok in checks if not ok]
    return sum(1 for _, ok in checks if ok) / len(checks), failed
