from __future__ import annotations

import io
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_report_clarity.v8"
_PATCH_MARKER = "_nico_comprehensive_report_clarity_v8"

_DEFAULT_REASONS = {
    "code_audit": "location review",
    "dependency_health": "candidate disposition",
    "secrets_review": "history coverage",
    "static_analysis": "analyzer coverage",
    "ci_cd": "workflow classification",
    "architecture_debt": "hotspot review",
    "velocity_complexity": "trend history",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _assurance_reason(section: dict[str, Any]) -> str:
    combined = " ".join(
        _text(item).casefold()
        for field in ("unavailable", "findings")
        for item in section.get(field) or []
    )
    if any(token in combined for token in ("gitleaks", "trufflehog", "full history", "history coverage")):
        return "history coverage"
    if any(token in combined for token in ("bandit", "semgrep", "eslint", "typescript", "analyzer")):
        return "analyzer coverage"
    if any(token in combined for token in ("workflow", "ci failure", "cause classification", "historical ci")):
        return "workflow classification"
    if any(token in combined for token in ("trend", "baseline history", "historical trend")):
        return "trend history"
    if any(token in combined for token in ("candidate", "triage", "disposition")):
        return "candidate disposition"
    if any(token in combined for token in ("hotspot", "complexity", "location review")):
        return "hotspot review"
    return _DEFAULT_REASONS.get(_text(section.get("id")), "evidence closure")


def clarify_comprehensive_assurance(assessment: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, dict)]
    display_by_id: dict[str, str] = {}
    for section in sections:
        canonical = _text(section.get("assurance_label") or section.get("assurance_status") or "PENDING").upper()
        reason = _assurance_reason(section)
        if canonical == "VERIFIED":
            display = "VERIFIED"
            reason = "required evidence accepted"
        elif canonical in {"BLOCKED", "INCOMPLETE", "UNAVAILABLE"}:
            display = canonical
        elif canonical in {"PENDING HUMAN APPROVAL", "SUPPLEMENTAL"}:
            display = canonical
        else:
            display = f"LIMITED · {reason.upper()}"
        section["assurance_reason"] = reason
        section["assurance_display"] = display
        display_by_id[_text(section.get("id"))] = display

    for row in assessment.get("scoring_weights") or []:
        if not isinstance(row, dict):
            continue
        section_id = _text(row.get("section_id"))
        if section_id in display_by_id:
            row["assurance_canonical"] = row.get("assurance")
            row["assurance"] = display_by_id[section_id]

    assessment["assurance_legend"] = {
        "verified": "All required evidence for the control was accepted for the exact assessed snapshot.",
        "limited": "The technical score is usable, but a named evidence or triage requirement remains open.",
        "incomplete": "A required evidence path did not complete and the control cannot support full assurance.",
        "technical_score_independent": True,
        "version": VERSION,
    }
    return assessment


def _wrap_lines(text: str, width: float, font_name: str, font_size: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    words = _text(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _front_matter_correction(assessment: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.showPage()

    risks = [
        _text(item.get("title"))
        for item in assessment.get("executive_risk_register") or []
        if isinstance(item, dict) and _text(item.get("title"))
    ][:3]
    if not risks:
        risks = [
            "Complete exact-package human review",
            "Close named evidence limitations",
            "Approve the sequenced remediation plan",
        ]

    white = colors.white
    border = colors.HexColor("#cbd5e1")
    ink = colors.HexColor("#0f172a")
    slate = colors.HexColor("#475569")
    pale = colors.HexColor("#f0f9ff")
    cyan = colors.HexColor("#0284c7")

    page.setFillColor(white)
    page.rect(34, 132, 544, 190, stroke=0, fill=1)
    page.setFillColor(pale)
    page.setStrokeColor(border)
    page.roundRect(42, 145, 528, 162, 11, stroke=1, fill=1)
    page.setFillColor(cyan)
    page.setFont("Helvetica-Bold", 8)
    page.drawString(58, 286, "TOP BUSINESS CONSEQUENCES")
    page.setFillColor(ink)
    page.setFont("Helvetica-Bold", 15)
    page.drawString(58, 263, "Decision-relevant issues to address first")

    y = 235
    for index, risk in enumerate(risks, 1):
        page.setFillColor(cyan)
        page.circle(66, y + 2, 9, stroke=0, fill=1)
        page.setFillColor(white)
        page.setFont("Helvetica-Bold", 8)
        page.drawCentredString(66, y - 1, str(index))
        page.setFillColor(slate)
        page.setFont("Helvetica", 8.2)
        lines = _wrap_lines(risk, 462, "Helvetica", 8.2)[:2]
        line_y = y + 5
        for line in lines:
            page.drawString(84, line_y, line)
            line_y -= 10
        y -= 38

    page.save()
    return buffer.getvalue()


def _polish_overlay(original_bytes: bytes, assessment: dict[str, Any]) -> bytes:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(original_bytes))
    correction = PdfReader(io.BytesIO(_front_matter_correction(assessment)))
    if len(reader.pages) > 1 and len(correction.pages) > 1:
        reader.pages[1].merge_page(correction.pages[1], over=True)
    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_comprehensive_report_clarity_v8() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_express_quality_v7 as quality

    current_reconcile: Callable[[dict[str, Any]], dict[str, Any]] = report.reconcile_comprehensive_assessment
    current_overlay: Callable[..., bytes] = quality._front_matter_overlay
    if getattr(current_reconcile, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current_reconcile)
    def reconcile(assessment: dict[str, Any]) -> dict[str, Any]:
        return clarify_comprehensive_assurance(current_reconcile(assessment))

    @wraps(current_overlay)
    def overlay(identity: dict[str, Any], assessment: dict[str, Any], limitations: dict[str, int], generated_at: str, final_page_count: int) -> bytes:
        return _polish_overlay(
            current_overlay(identity, assessment, limitations, generated_at, final_page_count),
            assessment,
        )

    setattr(reconcile, _PATCH_MARKER, True)
    setattr(overlay, _PATCH_MARKER, True)
    report.reconcile_comprehensive_assessment = reconcile
    quality._front_matter_overlay = overlay
    return {
        "status": "installed",
        "version": VERSION,
        "canonical_assurance_unchanged": True,
        "named_assurance_reason_added": True,
        "generic_review_limited_table_reduced": True,
        "top_business_consequences_reflowed": True,
        "technical_scores_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "clarify_comprehensive_assurance",
    "install_comprehensive_report_clarity_v8",
]
