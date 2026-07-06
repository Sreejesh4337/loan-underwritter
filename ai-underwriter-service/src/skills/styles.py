"""Shared visual constants for the memo and cash-flow generators, so the two
"skills" render decisions with a consistent color language."""

from __future__ import annotations

from reportlab.lib import colors

from src.schemas.underwriting import Decision

BADGE_COLORS = {
    Decision.APPROVE: colors.HexColor("#1e7e34"),
    Decision.REFER: colors.HexColor("#b8860b"),
    Decision.DECLINE: colors.HexColor("#a71d2a"),
}

# Hex strings for openpyxl PatternFill (no leading '#')
BADGE_FILL_HEX = {
    Decision.APPROVE: "1E7E34",
    Decision.REFER: "B8860B",
    Decision.DECLINE: "A71D2A",
}
