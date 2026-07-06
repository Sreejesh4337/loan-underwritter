"""Resolves an application_id to its input file paths under docs/applications/
— shared by the CLI, the API, and the eval harness so there's one place that
knows this convention."""

from __future__ import annotations

from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "applications"


def resolve_input_paths(application_id: str) -> dict[str, str]:
    app_dir = DOCS_DIR / application_id
    return {
        "bank_statement": str(app_dir / "bank_statement.pdf"),
        "kyc_and_credit": str(app_dir / "kyc_and_credit.pdf"),
        "income_details": str(app_dir / "income_details.xlsx"),
    }
