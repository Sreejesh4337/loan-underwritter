"""Shared exceptions and helpers for the deterministic parser layer.

Parsers turn raw application-packet files (PDF/Excel) into clean, well-organized
text or unambiguous structured data. They never call an LLM. Interpreting that
output into typed Pydantic objects (the "pull out the numbers" step) is the
job of `src/extractors/`.
"""

from __future__ import annotations


class ParserError(Exception):
    """Raised when a document cannot be parsed at all (missing/corrupt/unreadable).

    Callers (graph nodes) should catch this, try the fallback parser if one
    exists, and otherwise route to the bad-input handling path rather than
    letting the run crash.
    """
