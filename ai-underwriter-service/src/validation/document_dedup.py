"""Document deduplication service.

Computes SHA-256 fingerprints of uploaded files and checks them against the
``document_fingerprints`` table in the database to enforce a configurable
cooldown period (default 90 days).  If *any* of the uploaded documents is
still within its cooldown window, the entire upload is blocked — a standard
safeguard in banking/fintech underwriting workflows.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel

from src.db import check_document_cooldown


class DuplicateInfo(BaseModel):
    """Details about a document that is still within its cooldown window."""

    doc_type: str
    previous_application_id: str
    processed_at: str
    cooldown_until: str
    days_remaining: int


def compute_file_hash(content: bytes) -> str:
    """Return the hex SHA-256 digest of *content*."""
    return hashlib.sha256(content).hexdigest()


def check_duplicates(
    documents: dict[str, bytes],
) -> dict[str, DuplicateInfo]:
    """Check each document for an active cooldown.

    Parameters
    ----------
    documents:
        Mapping of ``doc_type`` → raw file bytes, e.g.
        ``{"bank_statement": b"...", "kyc_and_credit": b"...", ...}``.

    Returns
    -------
    dict[str, DuplicateInfo]
        A mapping of ``doc_type`` → duplicate details for every document
        whose fingerprint is already in the database and still within the
        cooldown window.  An empty dict means all documents are clear.
    """
    duplicates: dict[str, DuplicateInfo] = {}

    for doc_type, content in documents.items():
        file_hash = compute_file_hash(content)
        existing = check_document_cooldown(file_hash, doc_type)

        if existing is not None:
            cooldown_until_dt = datetime.fromisoformat(existing["cooldown_until"])
            now = datetime.now(timezone.utc)
            days_remaining = max(0, (cooldown_until_dt - now).days)

            duplicates[doc_type] = DuplicateInfo(
                doc_type=doc_type,
                previous_application_id=existing["application_id"],
                processed_at=existing["processed_at"],
                cooldown_until=existing["cooldown_until"],
                days_remaining=days_remaining,
            )

    return duplicates
