"""Underwriting memo PDF generator.

A plain, deterministic Python function (a LangChain-callable "skill" in
name, not a literal instruction-interpreted Skill folder — see this
project's plan for the rationale: a compliance document that must always
contain the same required sections is a poor fit for LLM-interpreted,
non-deterministic generation). No LLM calls, no I/O beyond writing the one
output file — this makes it trivially unit-testable with a hand-built
UnderwritingResult fixture.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.schemas.underwriting import UnderwritingResult
from src.skills.styles import BADGE_COLORS

_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("MemoTitle", parent=_STYLES["Title"], fontSize=18, spaceAfter=4)
_STRAP_STYLE = ParagraphStyle(
    "Strap", parent=_STYLES["Normal"], textColor=colors.HexColor("#a71d2a"), fontSize=8, spaceAfter=10
)
_SECTION_STYLE = ParagraphStyle("Section", parent=_STYLES["Heading2"], spaceBefore=14, spaceAfter=6)
_BODY_STYLE = _STYLES["Normal"]
_FOOTER_STYLE = ParagraphStyle("Footer", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey)

_KV_TABLE_STYLE = TableStyle(
    [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f4f4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(
        2 * cm,
        1.2 * cm,
        "AI-generated recommendation. A human underwriter must review before any action is taken. "
        "No real personal data.",
    )
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    table = Table([[k, v] for k, v in rows], colWidths=[5.5 * cm, 10 * cm])
    table.setStyle(_KV_TABLE_STYLE)
    return table


def _decision_badge(result: UnderwritingResult) -> Table:
    label = result.decision.value.upper()
    badge = Table([[label]], colWidths=[6 * cm])
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), BADGE_COLORS[result.decision]),
                ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
                ("FONTSIZE", (0, 0), (0, 0), 16),
                ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("TOPPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, 0), (0, 0), 10),
            ]
        )
    )
    return badge


def generate_underwriting_memo(result: UnderwritingResult, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )
    story = []

    story.append(Paragraph("Underwriting Memo", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"CONFIDENTIAL — SYNTHETIC DATA · Application {result.application_id} · Run {result.run_id} · "
            f"Generated {result.generated_at:%Y-%m-%d %H:%M} UTC",
            _STRAP_STYLE,
        )
    )

    story.append(Paragraph("Applicant Summary", _SECTION_STYLE))
    story.append(
        _kv_table(
            [
                ("Full name", result.applicant.full_name),
                ("Employment type", result.applicant.employment_type.value.replace("_", "-").title()),
                ("Employer / business", result.applicant.employer_or_business or "-"),
                ("Product", result.loan_request.product),
                ("Requested amount", f"INR {result.loan_request.requested_amount:,.0f}"),
                ("Tenor", f"{result.loan_request.tenor_months} months"),
                ("Indicative rate", f"{result.loan_request.indicative_rate_pct:.1f}% p.a."),
            ]
        )
    )

    story.append(Paragraph("Key Financial Metrics", _SECTION_STYLE))
    m = result.metrics
    salary_row = (
        [("Salary credit months (of 6)", str(m.salary_credit_months_count))]
        if m.salary_credit_months_count is not None
        else []
    )
    story.append(
        _kv_table(
            [
                ("Net monthly income", f"INR {m.net_monthly_income:,.0f} ({m.net_monthly_income_source})"),
                ("Existing EMIs", f"INR {m.existing_emis:,.0f}"),
                ("Proposed EMI", f"INR {m.proposed_emi:,.0f}"),
                ("FOIR", f"{m.foir_pct:.1f}%"),
                ("Credit score", str(result.credit_bureau.credit_score)),
                ("Average bank balance", f"INR {m.avg_bank_balance:,.0f}"),
                ("Payment returns", str(m.payment_returns_count)),
                *salary_row,
                ("Vintage", f"{m.vintage_months} months"),
                ("Unexplained large cash deposit", "Yes" if m.unexplained_cash_deposit_flag else "No"),
            ]
        )
    )

    story.append(Paragraph("Decision", _SECTION_STYLE))
    story.append(_decision_badge(result))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Reasons", _SECTION_STYLE))
    fired = [r for r in result.fired_rules if r.fired]
    if fired:
        for i, rule in enumerate(fired, start=1):
            story.append(Paragraph(f"{i}. ({rule.rule_id}) {rule.message}", _BODY_STYLE))
    else:
        story.append(Paragraph("No decline or refer rules fired; approved by default.", _BODY_STYLE))

    if result.rationale_text:
        story.append(Paragraph("Underwriter Narrative", _SECTION_STYLE))
        story.append(Paragraph(result.rationale_text, _BODY_STYLE))

    if result.advisory_notes:
        story.append(Paragraph("Advisory Notes", _SECTION_STYLE))
        for note in result.advisory_notes:
            story.append(Paragraph(f"• {note}", _BODY_STYLE))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output_path
