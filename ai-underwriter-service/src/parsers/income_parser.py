"""Parser for the income_details.xlsx sheet.

Confirmed by direct inspection of the sample files (raw XML + openpyxl on all
15 apps) that this file has **two distinct layouts** depending on
`Employment type`, matching the policy's two different net-income sources:

- Salaried: header key/value rows (Applicant, Applicant ID, Employment type,
  Employer, Months at current job), then a monthly table (Month, Basic, HRA,
  Allowances, Deductions, Net pay (INR)), then an "Average net pay" row.
- Self-employed: header key/value rows (Applicant, Applicant ID, Employment
  type, Business name, Months in business, Nature), then a small "Item" /
  "Value" table containing "Declared monthly income (INR)", "Annual GST
  turnover (INR)", and "Avg monthly bank credits (INR)" — the field the
  lending policy actually calls for as net monthly income for self-employed
  applicants.

Both layouts are plain shared-strings / numeric cells with no merged cells or
formulas — openpyxl reads either with zero special-casing beyond detecting
which table follows the header rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from .base import ParserError

MONTHLY_TABLE_HEADER = "Month"
BUSINESS_TABLE_HEADER = "Item"
AVERAGE_ROW_LABEL = "Average net pay"


@dataclass
class ParsedIncomeDocument:
    header_fields: dict[str, str]
    monthly_table_header: list[str] = field(default_factory=list)
    monthly_rows: list[list[Any]] = field(default_factory=list)
    average_net_pay: float | None = None
    business_items: dict[str, str] = field(default_factory=dict)
    source_file: str = ""


def parse_income_xlsx(path: Path) -> ParsedIncomeDocument:
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    except Exception as exc:
        raise ParserError(f"failed to parse income sheet {path}: {exc}") from exc

    header_fields: dict[str, str] = {}
    monthly_table_header: list[str] = []
    monthly_rows: list[list[Any]] = []
    average_net_pay: float | None = None
    business_items: dict[str, str] = {}

    mode = "header"  # header -> monthly_table | business_table -> header (post-table rows, if any)
    for row in rows:
        cells = [c for c in row if c is not None]
        if not cells:
            continue
        first = str(cells[0]).strip()

        if first == MONTHLY_TABLE_HEADER:
            monthly_table_header = [str(c).strip() for c in cells]
            mode = "monthly_table"
            continue
        if first == BUSINESS_TABLE_HEADER:
            mode = "business_table"
            continue
        if first == AVERAGE_ROW_LABEL:
            average_net_pay = float(cells[1])
            mode = "header"
            continue

        if mode == "monthly_table":
            monthly_rows.append(cells)
        elif mode == "business_table" and len(cells) == 2:
            business_items[str(cells[0]).strip()] = str(cells[1]).strip()
        elif mode == "header" and len(cells) == 2:
            header_fields[first] = str(cells[1]).strip()
        # anything else (stray title rows, blank separators) is silently skipped

    if not header_fields:
        raise ParserError(f"income sheet {path} produced no header fields")
    if not monthly_rows and not business_items:
        raise ParserError(f"income sheet {path} produced neither a monthly table nor a business income table")

    return ParsedIncomeDocument(
        header_fields=header_fields,
        monthly_table_header=monthly_table_header,
        monthly_rows=monthly_rows,
        average_net_pay=average_net_pay,
        business_items=business_items,
        source_file=str(path),
    )
