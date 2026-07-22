from __future__ import annotations

import io
from copy import deepcopy
from typing import Any

VERSION = "nico.comprehensive_express_quality.v7"


def _text(value: Any, limit: int = 2400) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _band(score: int | None) -> tuple[str, str]:
    if score is None:
        return "not_scored", "NOT SCORED"
    if score >= 90:
        return "exceptional", "EXCEPTIONAL"
    if score >= 80:
        return "strong", "STRONG"
    if score >= 70:
        return "moderate", "MODERATE"
    if score >= 55:
        return "weak", "WEAK"
    return "critical", "CRITICAL"


def reconcile_comprehensive_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    """Preserve Comprehensive depth while reusing the accepted shared-control truth model."""
    from nico import comprehensive_premium_synthesis_v6 as premium
    from nico.express_static_scanner_velocity_scoring_v44 import (
        apply_express_static_scanner_velocity_scoring_v44,
    )
    from nico.express_truth_calibration_v36 import calibrate_express_truth

    output = premium.polish_assessment(deepcopy(assessment))
    output = calibrate_express_truth(output)
    output = apply_express_static_scanner_velocity_scoring_v44(output)

    sections = [item for item in output.get("sections") or [] if isinstance(item, dict)]
    technical_score, weighting = premium._weighted_maturity(sections)
    band_key, band_label = _band(technical_score)
    adjusted = output.get("evidence_adjusted_score")
    if not isinstance(adjusted, (int, float)):
        adjusted = technical_score

    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    maturity.update(
        {
            "score": technical_score,
            "source_score": technical_score,
            "presented_score": technical_score,
            "technical_score": technical_score,
            "evidence_adjusted_score": int(adjusted) if isinstance(adjusted, (int, float)) else None,
            "score_band": band_key,
            "score_band_label": band_label,
            "scoring_method": "comprehensive_shared_truth_weighted_scored_controls_v7",
            "unscored_controls_excluded": [row["section_id"] for row in weighting if not row["included"]],
        }
    )
    output["maturity_signal"] = maturity
    output["technical_score"] = technical_score
    output["evidence_adjusted_score"] = int(adjusted) if isinstance(adjusted, (int, float)) else None
    output["scoring_weights"] = weighting

    repository = output.get("repository") or "the authorized repository"
    technical_text = "not scored" if technical_score is None else f"{technical_score}/100"
    adjusted_text = "not scored" if adjusted is None else f"{int(adjusted)}/100"
    output["executive_summary"] = (
        f"NICO completed an authorized Comprehensive Technical Assessment for {repository}. "
        f"Weighted technical maturity is {technical_text}; independently evidence-adjusted readiness is {adjusted_text}. "
        "The Comprehensive package retains the Express technical-health baseline and adds exact-location findings, deeper architecture evidence, "
        "a six-month execution roadmap, staffing sequence, and a full evidence appendix. Human review and exact-package approval remain mandatory."
    )
    output["comprehensive_express_quality"] = {
        "status": "complete",
        "version": VERSION,
        "shared_control_truth_reconciled": True,
        "static_bounded_score_supported_when_minimum_evidence_is_accepted": True,
        "scanner_execution_coverage_excluded_from_maturity": True,
        "technical_and_evidence_adjusted_scores_separated": True,
        "comprehensive_scope_extends_express_baseline": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def _wrap_lines(text: Any, width: float, font_name: str, font_size: float, max_lines: int | None = None) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    words = _text(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if max_lines and len(lines) >= max_lines:
            break
    if current and (not max_lines or len(lines) < max_lines):
        lines.append(current)
    if max_lines and len(lines) == max_lines and words:
        last = lines[-1]
        while last and stringWidth(last + "...", font_name, font_size) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
    return lines


def _draw_wrapped(
    canvas: Any,
    text: Any,
    x: float,
    y: float,
    width: float,
    *,
    font_name: str = "Helvetica",
    font_size: float = 9,
    leading: float = 12,
    color: Any = None,
    max_lines: int | None = None,
) -> float:
    if color is not None:
        canvas.setFillColor(color)
    canvas.setFont(font_name, font_size)
    for line in _wrap_lines(text, width, font_name, font_size, max_lines=max_lines):
        canvas.drawString(x, y, line)
        y -= leading
    return y


def _front_matter_overlay(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    limitations: dict[str, int],
    generated_at: str,
    final_page_count: int,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    width, height = letter
    navy = colors.HexColor("#020617")
    panel = colors.HexColor("#0f1c38")
    panel_border = colors.HexColor("#224166")
    cyan = colors.HexColor("#38bdf8")
    teal = colors.HexColor("#2dd4bf")
    white = colors.white
    muted = colors.HexColor("#a9b6c9")
    ink = colors.HexColor("#0f172a")
    slate = colors.HexColor("#475569")
    pale = colors.HexColor("#e0f2fe")
    line = colors.HexColor("#cbd5e1")

    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical = assessment.get("technical_score", maturity.get("score"))
    adjusted = assessment.get("evidence_adjusted_score", maturity.get("evidence_adjusted_score"))
    technical_display = "N/S" if not isinstance(technical, (int, float)) else f"{int(technical)}/100"
    adjusted_display = "N/S" if not isinstance(adjusted, (int, float)) else f"{int(adjusted)}/100"
    repository = _text(identity.get("repository"), 90)
    commit = _text(identity.get("commit_sha"), 64)
    risks = [item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)]
    top_risks = [_text(item.get("title"), 150) for item in risks[:3]]
    if not top_risks:
        top_risks = ["Complete exact-package human review", "Resolve retained evidence limitations", "Approve the six-month execution sequence"]

    # Page 1 - premium cover aligned with the Express visual standard.
    page.setFillColor(navy)
    page.rect(0, 0, width, height, stroke=0, fill=1)
    page.setFillColor(cyan)
    page.rect(0, height - 9, width * .72, 9, stroke=0, fill=1)
    page.setFillColor(teal)
    page.rect(width * .72, height - 9, width * .28, 9, stroke=0, fill=1)
    page.setFillColor(colors.HexColor("#082f49"))
    page.circle(width + 8, height - 50, 145, stroke=0, fill=1)
    page.setFillColor(colors.HexColor("#083344"))
    page.circle(12, -15, 125, stroke=0, fill=1)

    page.setFillColor(cyan)
    page.setFont("Helvetica-Bold", 9)
    page.drawString(42, 741, "NICO / EVIDENCE-BOUND ENGINEERING INTELLIGENCE")
    page.setFillColor(white)
    page.setFont("Helvetica-Bold", 31)
    page.drawString(42, 683, "NICO COMPREHENSIVE")
    page.setFillColor(muted)
    page.setFont("Helvetica", 15)
    page.drawString(42, 651, "Decision-Grade Technical Assessment")

    cards = [
        ("TECHNICAL MATURITY", technical_display, cyan),
        ("EVIDENCE-ADJUSTED", adjusted_display, teal),
        ("REVIEW POSTURE", "Required", colors.HexColor("#fbbf24")),
        ("DELIVERY", "Draft only", colors.HexColor("#f472b6")),
    ]
    card_y = 552
    card_w = 124
    for index, (label, value, accent) in enumerate(cards):
        x = 42 + index * 137
        page.setFillColor(panel)
        page.setStrokeColor(panel_border)
        page.roundRect(x, card_y, card_w, 78, 12, stroke=1, fill=1)
        page.setFillColor(accent)
        page.setFont("Helvetica-Bold", 8)
        page.drawString(x + 14, card_y + 55, label)
        page.setFillColor(white)
        page.setFont("Helvetica-Bold", 21 if "/100" in value else 19)
        page.drawString(x + 14, card_y + 22, value)

    page.setFillColor(panel)
    page.setStrokeColor(panel_border)
    page.roundRect(42, 444, 528, 82, 13, stroke=1, fill=1)
    page.setFillColor(cyan)
    page.setFont("Helvetica-Bold", 8)
    page.drawString(58, 500, "ASSESSED REPOSITORY")
    page.setFillColor(white)
    page.setFont("Helvetica-Bold", 15)
    page.drawString(58, 475, repository)
    page.setFillColor(muted)
    page.setFont("Helvetica", 7)
    page.drawString(58, 456, commit)
    page.drawRightString(552, 456, generated_at)

    page.setFillColor(white)
    page.setFont("Helvetica-Bold", 18)
    page.drawString(42, 401, "Executive posture")
    summary = assessment.get("executive_summary") or (
        f"NICO completed an authorized Comprehensive Technical Assessment for {repository}. "
        "The package adds deeper architecture, exact-location findings, roadmap, staffing, and evidence traceability to the Express baseline."
    )
    _draw_wrapped(page, summary, 42, 378, 528, font_size=8.4, leading=12, color=muted, max_lines=5)

    page.setFillColor(panel)
    page.setStrokeColor(panel_border)
    page.roundRect(42, 112, 528, 188, 13, stroke=1, fill=1)
    page.setFillColor(cyan)
    page.setFont("Helvetica-Bold", 8)
    page.drawString(58, 276, "PRIORITY DECISIONS")
    y = 247
    for index, risk in enumerate(top_risks, 1):
        page.setFillColor(teal)
        page.circle(64, y + 3, 8, stroke=0, fill=1)
        page.setFillColor(navy)
        page.setFont("Helvetica-Bold", 8)
        page.drawCentredString(64, y, str(index))
        y = _draw_wrapped(page, risk, 82, y + 2, 458, font_size=8.8, leading=12, color=white, max_lines=2) - 11

    page.setFillColor(muted)
    page.setFont("Helvetica", 7)
    page.drawString(42, 68, "READ-ONLY · IMMUTABLE SNAPSHOT · HUMAN REVIEW REQUIRED")
    page.setFillColor(cyan)
    page.setFont("Helvetica-Bold", 7)
    page.drawRightString(570, 68, "POWERED BY REPARODYNAMICS")
    page.setFillColor(colors.HexColor("#fb7185"))
    page.drawString(42, 51, "Not approved for client delivery")
    page.setFillColor(white)
    page.drawRightString(570, 51, f"Page 1 of {final_page_count}")
    page.showPage()

    # Page 2 - executive decision brief and scope expansion.
    page.setFillColor(white)
    page.rect(0, 0, width, height, stroke=0, fill=1)
    page.setFillColor(ink)
    page.setFont("Helvetica-Bold", 25)
    page.drawCentredString(width / 2, 744, "Executive Decision Brief")
    y = _draw_wrapped(page, summary, 42, 713, 528, font_size=8.5, leading=11.5, color=slate, max_lines=4)

    page.setFillColor(pale)
    page.setStrokeColor(cyan)
    page.rect(42, y - 48, 528, 45, stroke=1, fill=1)
    page.setFillColor(colors.HexColor("#075985"))
    page.setFont("Helvetica-Bold", 8.2)
    page.drawString(53, y - 20, "COMPREHENSIVE DECISION BOUNDARY")
    _draw_wrapped(
        page,
        "This report preserves shared technical-health truth while adding deeper architecture, exact-location evidence, remediation sequencing, staffing, and acceptance criteria. More evidence may refine risk without converting uncertainty into failure.",
        53,
        y - 34,
        506,
        font_size=7.5,
        leading=9.5,
        color=colors.HexColor("#0c4a6e"),
        max_lines=2,
    )
    y -= 72

    page.setFillColor(colors.HexColor("#075985"))
    page.setFont("Helvetica-Bold", 16)
    page.drawString(42, y, "Decision dashboard")
    y -= 17
    rows = [
        ("Operate", "Continue inside the authorized scope while review-limited controls remain visible."),
        ("Release", "Conditional on disposition of P1 evidence, scanner exceptions, and exact-SHA acceptance checks."),
        ("Client delivery", "Blocked until an authorized reviewer accepts the exact report package and open limitations."),
        ("Immediate priority", top_risks[0]),
    ]
    row_h = 34
    page.setStrokeColor(line)
    for index, (label, value) in enumerate(rows):
        top = y - index * row_h
        page.setFillColor(colors.HexColor("#e0f2fe") if index == 0 else colors.HexColor("#f8fafc"))
        page.rect(42, top - row_h, 528, row_h, stroke=1, fill=1)
        page.setFillColor(slate)
        page.setFont("Helvetica-Bold", 7.5)
        page.drawString(51, top - 21, label)
        _draw_wrapped(page, value, 154, top - 14, 404, font_size=7.3, leading=9.2, color=slate, max_lines=2)
    y -= row_h * len(rows) + 24

    page.setFillColor(colors.HexColor("#075985"))
    page.setFont("Helvetica-Bold", 16)
    page.drawString(42, y, "Why this is broader than Express")
    y -= 17
    scope_cards = [
        ("DEEPER EVIDENCE", "Exact-location technical findings and full evidence traceability."),
        ("EXECUTION PLAN", "Six-month roadmap with owners, effort, acceptance, and impact."),
        ("RESOURCING", "Staffing sequence and capacity boundaries for implementation."),
        ("DELIVERY GATE", "Human acceptance checklist and immutable package identity."),
    ]
    card_w = 255
    card_h = 58
    for index, (label, value) in enumerate(scope_cards):
        col = index % 2
        row = index // 2
        x = 42 + col * 273
        top = y - row * 68
        page.setFillColor(colors.HexColor("#f8fafc"))
        page.setStrokeColor(line)
        page.roundRect(x, top - card_h, card_w, card_h, 7, stroke=1, fill=1)
        page.setFillColor(colors.HexColor("#0284c7"))
        page.setFont("Helvetica-Bold", 7.5)
        page.drawString(x + 10, top - 17, label)
        _draw_wrapped(page, value, x + 10, top - 32, card_w - 20, font_size=7.1, leading=9, color=slate, max_lines=3)
    y -= 145

    page.setFillColor(colors.HexColor("#075985"))
    page.setFont("Helvetica-Bold", 16)
    page.drawString(42, y, "Top business consequences")
    y -= 19
    for risk in top_risks:
        page.setFillColor(colors.HexColor("#0284c7"))
        page.circle(48, y + 3, 2.5, stroke=0, fill=1)
        y = _draw_wrapped(page, risk, 58, y + 6, 506, font_size=7.7, leading=10, color=slate, max_lines=2) - 6

    identity_y = 94
    page.setStrokeColor(line)
    page.line(42, identity_y + 34, 570, identity_y + 34)
    page.setFillColor(colors.HexColor("#075985"))
    page.setFont("Helvetica-Bold", 8)
    page.drawString(42, identity_y + 18, "PACKAGE IDENTITY")
    page.setFillColor(slate)
    page.setFont("Helvetica", 6.7)
    page.drawString(42, identity_y + 5, f"Run: {_text(identity.get('run_id'), 45)}")
    page.drawString(220, identity_y + 5, f"Limitations: {limitations.get('individual_limitation_records', 0)}")
    page.drawRightString(570, identity_y + 5, f"Final PDF pages: {final_page_count}")
    page.setFillColor(colors.HexColor("#64748b"))
    page.drawString(42, 45, "NICO Comprehensive · evidence-bound · report only · human review required")
    page.drawRightString(570, 45, f"Page 2 of {final_page_count}")
    page.save()
    return buffer.getvalue()


def _overlay_front_matter(pdf_bytes: bytes, overlay_bytes: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    overlay = PdfReader(io.BytesIO(overlay_bytes))
    for index in range(min(2, len(reader.pages), len(overlay.pages))):
        reader.pages[index].merge_page(overlay.pages[index], over=True)
    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def build_comprehensive_pdf(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
    final_page_count: int | None = None,
) -> bytes:
    from nico.comprehensive_decision_grade_pdf_v5 import _build_pdf as base_build_pdf
    from pypdf import PdfReader

    base = base_build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at, final_page_count)
    count = len(PdfReader(io.BytesIO(base)).pages)
    overlay = _front_matter_overlay(identity, assessment, limitations, generated_at, count)
    return _overlay_front_matter(base, overlay)


def comprehensive_pdf_with_final_count(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> tuple[bytes, int]:
    from nico.comprehensive_decision_grade_pdf_v5 import _build_pdf as base_build_pdf
    from pypdf import PdfReader

    first = base_build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    target = len(PdfReader(io.BytesIO(first)).pages)
    base = base_build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at, target)
    actual = len(PdfReader(io.BytesIO(base)).pages)
    if actual != target:
        target = actual
        base = base_build_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at, target)
        actual = len(PdfReader(io.BytesIO(base)).pages)
    overlay = _front_matter_overlay(identity, assessment, limitations, generated_at, actual)
    final = _overlay_front_matter(base, overlay)
    final_count = len(PdfReader(io.BytesIO(final)).pages)
    if final_count != actual:
        overlay = _front_matter_overlay(identity, assessment, limitations, generated_at, final_count)
        final = _overlay_front_matter(base, overlay)
        final_count = len(PdfReader(io.BytesIO(final)).pages)
    return final, final_count


__all__ = [
    "VERSION",
    "reconcile_comprehensive_assessment",
    "build_comprehensive_pdf",
    "comprehensive_pdf_with_final_count",
]
