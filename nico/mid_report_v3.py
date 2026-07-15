from __future__ import annotations

import base64
import html
import io
from copy import deepcopy
from typing import Any, Callable

MID_REPORT_V3_VERSION = "mid-assessment-decision-ready-v3"
PDF_STYLE_VERSION = "mid_report_v3_decision_ready"
_INSTALLED = False
_ORIGINAL_PAYLOAD: Callable[..., dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u2014", "-").replace("\u2013", "-").split())


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.lower().rstrip(" .;:")
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _section_map(items: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in items
        if isinstance(item, dict) and item.get("id")
    }


def _score_label(value: Any) -> str:
    try:
        return f"{int(float(value))}/100"
    except (TypeError, ValueError):
        return "Not scored"


def _status_color(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized == "verified":
        return "#047857"
    if "limitation" in normalized or "review" in normalized:
        return "#b45309"
    if normalized in {"failed", "unavailable"}:
        return "#b91c1c"
    return "#475569"


def _severity_color(value: Any) -> str:
    return {
        "critical": "#991b1b",
        "high": "#dc2626",
        "medium": "#d97706",
        "low": "#2563eb",
    }.get(str(value or "").lower(), "#64748b")


def _top_actions(repairs: dict[str, Any], assessment: dict[str, Any]) -> list[str]:
    actions = [
        str(item.get("recommended_action") or "")
        for item in _list(repairs.get("candidates"))
        if isinstance(item, dict) and item.get("recommended_action")
    ]
    if not actions:
        actions = [str(item) for item in _list(assessment.get("next_steps"))]
    actions.append("Complete human review of every consolidated exception before approval or client delivery.")
    return _unique(actions)[:6]


def build_mid_v3_payload(
    record: dict[str, Any],
    packet: dict[str, Any],
    identity: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    if _ORIGINAL_PAYLOAD is None:
        raise RuntimeError("Mid report payload delegate is unavailable.")
    payload = deepcopy(_ORIGINAL_PAYLOAD(record, packet, identity, generated_at))
    response = _dict(record.get("response"))
    assessment = deepcopy(_dict(response.get("assessment")))
    truth = _dict(response.get("mid_truth_status"))
    raw_sections = _section_map(_list(truth.get("sections")))

    for section in _list(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        raw = raw_sections.get(str(section.get("id") or ""), {})
        section["scope_disclosures"] = _unique(_list(raw.get("scope_disclosures")))
        section["verification_basis"] = raw.get("verification_basis") or ""
        for key in ("dependency_scanner_triage", "secret_history_triage", "static_triage", "score_evidence_breakdown"):
            if isinstance(raw.get(key), dict):
                section[key] = deepcopy(raw[key])

    from nico.report_repair_intelligence import build_report_repair_intelligence

    repair_source = deepcopy(assessment)
    repair_source["human_review_required"] = True
    repairs = build_report_repair_intelligence(repair_source)
    score = _dict(assessment.get("maturity_signal"))
    score_explanation = deepcopy(_dict(assessment.get("mid_score_explanation")))
    review_summary = deepcopy(_dict(packet.get("summary")))
    truth_summary = deepcopy(_dict(truth.get("summary")))
    top_constraints = _unique(_list(score_explanation.get("primary_score_constraints")))
    verified = [
        str(item.get("label") or item.get("id") or "")
        for item in _list(payload.get("sections"))
        if isinstance(item, dict) and str(item.get("truth_status") or "") == "Verified"
    ]

    payload.update(
        {
            "report_version": MID_REPORT_V3_VERSION,
            "pdf_style": PDF_STYLE_VERSION,
            "maturity_signal": score,
            "scorecard": deepcopy(_dict(assessment.get("scorecard"))),
            "mid_score_explanation": score_explanation,
            "repair_intelligence": repairs,
            "decision_summary": {
                "technical_score": score.get("score"),
                "maturity_level": score.get("level") or "Unclassified",
                "evidence_coverage_percent": _dict(payload.get("evidence_coverage")).get("percent", 0),
                "verified_sections": verified,
                "primary_score_constraints": top_constraints,
                "priority_actions": _top_actions(repairs, assessment),
                "review_items": _int(review_summary.get("items_requiring_review")),
                "duplicate_review_items_removed": _int(review_summary.get("consolidated_duplicate_items_removed")),
                "unsupported_claims_permitted": 0,
                "human_review_required": True,
            },
            "truth_summary": truth_summary,
            "report_only": True,
            "code_changes_applied": False,
            "automatic_approval_allowed": False,
            "client_delivery_allowed": False,
        }
    )
    executive = _dict(payload.get("executive_summary"))
    executive.update(
        {
            "technical_maturity": score.get("level") or "Unclassified",
            "technical_score": score.get("score"),
            "evidence_coverage": f"{_dict(payload.get('evidence_coverage')).get('percent', 0)}%",
            "verified_sections": truth_summary.get("sections_verified", truth_summary.get("verified", 0)),
            "verified_with_limitations": truth_summary.get("sections_verified_with_limitations", truth_summary.get("verified_with_limitations", 0)),
            "items_requiring_review": review_summary.get("items_requiring_review", 0),
            "client_delivery": "Human Review Required",
        }
    )
    payload["executive_summary"] = executive
    return payload


def decision_ready_markdown(payload: dict[str, Any]) -> str:
    decision = _dict(payload.get("decision_summary"))
    lines = [
        "# NICO MID ASSESSMENT",
        "",
        "**DRAFT - HUMAN REVIEW REQUIRED**",
        "",
        f"- Repository: `{payload.get('repository')}`",
        f"- Snapshot commit: `{payload.get('snapshot_commit_sha')}`",
        f"- Mid run: `{payload.get('run_id')}`",
        f"- Report: `{payload.get('report_id')}`",
        f"- Generated: {payload.get('generated_at')}",
        "",
        "## Executive decision brief",
        "",
        f"- Maturity: **{decision.get('maturity_level')}**",
        f"- Technical score: **{_score_label(decision.get('technical_score'))}**",
        f"- Evidence coverage: **{decision.get('evidence_coverage_percent')}%**",
        f"- Consolidated review items: **{decision.get('review_items')}**",
        f"- Unsupported claims permitted: **0**",
        "",
        "### Primary score constraints",
    ]
    constraints = _list(decision.get("primary_score_constraints"))
    lines.extend([f"- {item}" for item in constraints] or ["- No explicit score constraint was returned; human review still applies."])
    lines.extend(["", "### Priority actions"])
    lines.extend([f"- {item}" for item in _list(decision.get("priority_actions"))])

    contributions = _list(_dict(payload.get("mid_score_explanation")).get("contributions"))
    if contributions:
        lines.extend(["", "## Why the score is what it is", "", "| Area | Score | Weight | Weighted points |", "|---|---:|---:|---:|"])
        for item in contributions:
            if isinstance(item, dict):
                lines.append(f"| {item.get('label')} | {item.get('score')} | {item.get('weight')}% | {item.get('weighted_points')} |")

    coverage = _dict(payload.get("evidence_coverage"))
    lines.extend([
        "",
        "## Evidence coverage",
        "",
        f"**{coverage.get('percent', 0)}%** ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)} explicit evidence units)",
        "",
        str(coverage.get("method") or "Coverage is calculated from explicit exact-run evidence units."),
        "",
        "## Section scorecard",
        "",
        "| Section | Truth status | Score |", "|---|---|---:|",
    ])
    for section in _list(payload.get("sections")):
        if isinstance(section, dict):
            lines.append(f"| {section.get('label')} | {section.get('truth_status')} | {_score_label(section.get('score'))} |")

    for section in _list(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        lines.extend(["", f"## {section.get('label')}", "", f"- Truth status: **{section.get('truth_status')}**", f"- Score: {_score_label(section.get('score'))}", "", str(section.get("summary") or "")])
        if section.get("evidence"):
            lines.extend(["", "### Evidence"] + [f"- {item}" for item in _list(section.get("evidence"))])
        if section.get("findings"):
            lines.extend(["", "### Findings"] + [f"- {item}" for item in _list(section.get("findings"))])
        limitations = _unique([*_list(section.get("unavailable")), *_list(section.get("missing_evidence_sources")), *_list(section.get("failed_evidence_tools"))])
        if limitations:
            lines.extend(["", "### Blocking limitations"] + [f"- {item}" for item in limitations])
        if section.get("scope_disclosures"):
            lines.extend(["", "### Scope disclosures"] + [f"- {item}" for item in _list(section.get("scope_disclosures"))])

    repairs = _dict(payload.get("repair_intelligence"))
    lines.extend(["", "## Prioritized repair plan", ""])
    for item in _list(repairs.get("candidates"))[:8]:
        if not isinstance(item, dict):
            continue
        tgrm = _dict(item.get("tgrm"))
        lines.extend([
            f"### P{item.get('rank')} - {item.get('title')}",
            "",
            f"- Severity: {item.get('severity')}",
            f"- Priority: {item.get('priority_score')}",
            f"- Effort: {item.get('effort')}",
            f"- TGRM: Level {tgrm.get('level', '?')}",
            f"- Recommended action: {item.get('recommended_action')}",
            f"- Rollback: {item.get('rollback_plan')}",
            "",
        ])

    lines.extend(["## Consolidated human review", ""])
    for item in _list(_dict(payload.get("review_packet")).get("exceptions")):
        if isinstance(item, dict):
            lines.append(f"- **{item.get('severity', 'medium').upper()} - {item.get('title')}**: {item.get('reason')}")

    lines.extend([
        "",
        "## Safety and integrity",
        "",
        "- NICO did not modify the assessed repository.",
        "- Suggested repairs are report-only and remain unverified until exact-context tests pass.",
        "- Human approval is required before client delivery.",
        f"- Source identity SHA-256: `{payload.get('source_identity_sha256')}`",
        f"- Review packet SHA-256: `{_dict(payload.get('review_packet')).get('review_packet_sha256')}`",
    ])
    return "\n".join(lines).strip() + "\n"


def decision_ready_html(payload: dict[str, Any]) -> str:
    markdown = decision_ready_markdown(payload)
    escaped = html.escape(markdown)
    # The HTML export remains compact and mobile-readable while preserving the
    # complete Markdown as pre-wrapped evidence text.
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NICO Mid Assessment</title><style>
body{{font-family:Arial,sans-serif;max-width:1040px;margin:32px auto;padding:0 18px;color:#17202a;line-height:1.48;background:#f8fafc}}header{{padding:28px;border-radius:18px;background:#0f172a;color:white}}header b{{color:#67e8f9}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:white;border:1px solid #cbd5e1;border-radius:16px;padding:22px;font:14px/1.52 Arial,sans-serif}}.warning{{padding:12px 16px;border:1px solid #d97706;background:#fff7ed;color:#9a3412;border-radius:12px;font-weight:700;margin:16px 0}}@media(max-width:600px){{body{{margin:14px auto;padding:0 10px}}header{{padding:20px}}pre{{padding:14px;font-size:13px}}}}
</style></head><body><header><p><b>NICO - POWERED BY REPARODYNAMICS</b></p><h1>MID ASSESSMENT</h1><p>Decision-ready exact-snapshot technical assessment</p></header><p class="warning">DRAFT - HUMAN REVIEW REQUIRED - NO CLIENT DELIVERY</p><pre>{escaped}</pre></body></html>"""


def _paragraph(value: Any, style: Any, limit: int = 1800) -> Any:
    from reportlab.platypus import Paragraph

    text = _text(value)
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return Paragraph(html.escape(text), style)


def _bullets(values: list[Any], style: Any, max_items: int = 8) -> list[Any]:
    items = _unique(values)
    output: list[Any] = []
    for item in items[:max_items]:
        output.append(_paragraph(f"- {item}", style, 900))
    if len(items) > max_items:
        output.append(_paragraph(f"- {len(items) - max_items} additional item(s) remain in Markdown/HTML evidence exports.", style))
    return output


def decision_ready_pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.55 * inch, rightMargin=0.55 * inch, topMargin=0.5 * inch, bottomMargin=0.65 * inch, title="NICO Mid Assessment", author="NICO")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("MidV3Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.white, spaceAfter=8)
    subtitle = ParagraphStyle("MidV3Subtitle", parent=styles["BodyText"], fontSize=10, leading=13, textColor=colors.HexColor("#cbd5e1"))
    h1 = ParagraphStyle("MidV3H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=6, keepWithNext=True)
    h2 = ParagraphStyle("MidV3H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#0f172a"), spaceBefore=6, spaceAfter=4, keepWithNext=True)
    body = ParagraphStyle("MidV3Body", parent=styles["BodyText"], fontSize=8.2, leading=10.5, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("MidV3Small", parent=body, fontSize=7.2, leading=8.8, textColor=colors.HexColor("#475569"))
    label = ParagraphStyle("MidV3Label", parent=small, fontName="Helvetica-Bold", textColor=colors.HexColor("#334155"))
    warning = ParagraphStyle("MidV3Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#9a3412"), backColor=colors.HexColor("#fff7ed"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=7, spaceAfter=8)
    callout = ParagraphStyle("MidV3Callout", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#38bdf8"), borderWidth=0.7, borderPadding=7, spaceAfter=8)

    def table(rows: list[list[Any]], widths: list[float], header: str = "#e0f2fe") -> Any:
        value = Table(rows, colWidths=widths, repeatRows=1)
        value.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return value

    decision = _dict(payload.get("decision_summary"))
    coverage = _dict(payload.get("evidence_coverage"))
    story: list[Any] = []
    cover = Table([[
        _paragraph("NICO\nMID ASSESSMENT", title),
        _paragraph("POWERED BY REPARODYNAMICS\nDecision-ready exact-snapshot technical assessment", subtitle),
    ]], colWidths=[2.25 * inch, 4.55 * inch])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 22),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 22),
    ]))
    story.extend([cover, Spacer(1, 0.12 * inch), _paragraph("DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY BLOCKED", warning)])
    meta_rows = [
        [_paragraph("Repository", label), _paragraph(payload.get("repository"), small), _paragraph("Snapshot", label), _paragraph(str(payload.get("snapshot_commit_sha") or "")[:16], small)],
        [_paragraph("Client", label), _paragraph(payload.get("client_name") or "Not provided", small), _paragraph("Project", label), _paragraph(payload.get("project_name") or "Not provided", small)],
        [_paragraph("Mid run", label), _paragraph(payload.get("run_id"), small), _paragraph("Generated", label), _paragraph(payload.get("generated_at"), small)],
    ]
    story.append(table([[_paragraph("Identity", label), _paragraph("Value", label), _paragraph("Identity", label), _paragraph("Value", label)], *meta_rows], [0.75 * inch, 2.65 * inch, 0.75 * inch, 2.65 * inch]))
    story.append(Spacer(1, 0.12 * inch))
    score_rows = [[_paragraph("Maturity", label), _paragraph("Technical score", label), _paragraph("Evidence coverage", label), _paragraph("Review items", label)], [
        _paragraph(decision.get("maturity_level"), h1),
        _paragraph(_score_label(decision.get("technical_score")), h1),
        _paragraph(f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})", h1),
        _paragraph(decision.get("review_items"), h1),
    ]]
    story.append(table(score_rows, [1.7 * inch] * 4, header="#cffafe"))
    story.extend([Spacer(1, 0.08 * inch), _paragraph("Executive decision brief", h1)])
    constraints = _list(decision.get("primary_score_constraints"))
    story.append(_paragraph("The score is evidence-derived rather than target-derived. The following final exact-run constraints explain why the result is not higher:", callout))
    story.extend(_bullets(constraints or ["No explicit score constraint was returned; human review remains required."], body, 7))
    story.append(_paragraph("Priority actions", h2))
    story.extend(_bullets(_list(decision.get("priority_actions")), body, 6))

    contributions = [item for item in _list(_dict(payload.get("mid_score_explanation")).get("contributions")) if isinstance(item, dict)]
    if contributions:
        story.append(_paragraph("Why the technical score is what it is", h2))
        rows = [[_paragraph("Area", label), _paragraph("Score", label), _paragraph("Weight", label), _paragraph("Weighted points", label)]]
        for item in contributions:
            rows.append([_paragraph(item.get("label"), small), _paragraph(item.get("score"), small), _paragraph(f"{item.get('weight')}%", small), _paragraph(item.get("weighted_points"), small)])
        story.append(table(rows, [3.35 * inch, 0.8 * inch, 0.8 * inch, 1.25 * inch]))

    story.append(PageBreak())
    story.append(_paragraph("Section scorecard", h1))
    score_rows = [[_paragraph("Section", label), _paragraph("Truth status", label), _paragraph("Score", label), _paragraph("Evidence", label)]]
    for section in _list(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        score_rows.append([
            _paragraph(section.get("label"), small),
            _paragraph(section.get("truth_status"), small),
            _paragraph(_score_label(section.get("score")), small),
            _paragraph(f"{len(_list(section.get('evidence')))} item(s)", small),
        ])
    story.append(table(score_rows, [2.75 * inch, 1.55 * inch, 0.85 * inch, 1.65 * inch]))

    for section in _list(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        status = section.get("truth_status") or "Unavailable"
        heading = ParagraphStyle(f"MidSection{len(story)}", parent=h1, textColor=colors.HexColor(_status_color(status)))
        story.extend([Spacer(1, 0.05 * inch), _paragraph(f"{section.get('label')} - {status} - {_score_label(section.get('score'))}", heading), _paragraph(section.get("summary"), body)])
        if section.get("evidence"):
            story.append(_paragraph("Evidence", h2))
            story.extend(_bullets(_list(section.get("evidence")), small, 8))
        if section.get("findings"):
            story.append(_paragraph("Findings", h2))
            story.extend(_bullets(_list(section.get("findings")), small, 6))
        limitations = _unique([*_list(section.get("unavailable")), *_list(section.get("missing_evidence_sources")), *_list(section.get("failed_evidence_tools"))])
        if limitations:
            story.append(_paragraph("Blocking limitations", h2))
            story.extend(_bullets(limitations, small, 6))
        if section.get("scope_disclosures"):
            story.append(_paragraph("Scope disclosures", h2))
            story.extend(_bullets(_list(section.get("scope_disclosures")), small, 5))

    story.append(PageBreak())
    story.append(_paragraph("Prioritized repair plan", h1))
    repairs = _dict(payload.get("repair_intelligence"))
    candidates = [item for item in _list(repairs.get("candidates")) if isinstance(item, dict)]
    if not candidates:
        story.append(_paragraph("No ranked technical repair candidate was produced from the final evidence. Human review remains required.", body))
    for item in candidates[:8]:
        tgrm = _dict(item.get("tgrm"))
        severity = str(item.get("severity") or "unknown")
        heading = ParagraphStyle(f"MidRepair{len(story)}", parent=h2, textColor=colors.HexColor(_severity_color(severity)))
        story.append(_paragraph(f"P{item.get('rank')} - {item.get('title')}", heading))
        meta = [[_paragraph("Severity", label), _paragraph("Priority", label), _paragraph("Effort", label), _paragraph("TGRM", label)], [
            _paragraph(severity.upper(), small), _paragraph(item.get("priority_score"), small), _paragraph(str(item.get("effort") or "unknown").upper(), small), _paragraph(f"Level {tgrm.get('level', '?')}", small),
        ]]
        story.append(table(meta, [1.7 * inch] * 4, header="#f1f5f9"))
        story.extend([_paragraph(f"Impact: {item.get('impact') or item.get('technical_impact') or 'Review required.'}", body), _paragraph(f"Recommended action: {item.get('recommended_action') or 'Human-review the finding.'}", body)])
        if item.get("evidence"):
            story.extend(_bullets(_list(item.get("evidence")), small, 4))
        story.append(_paragraph(f"Rollback: {item.get('rollback_plan') or 'Revert only the approved bounded change if verification fails.'}", small))

    story.append(PageBreak())
    story.append(_paragraph("Consolidated human review", h1))
    exceptions = [item for item in _list(_dict(payload.get("review_packet")).get("exceptions")) if isinstance(item, dict)]
    story.append(_paragraph(f"{len(exceptions)} consolidated item(s) require an explicit human disposition. Duplicate limited-conclusion and score-effect cards are merged by section without dropping blockers or evidence.", callout))
    for item in exceptions:
        heading = ParagraphStyle(f"MidException{len(story)}", parent=h2, textColor=colors.HexColor(_severity_color(item.get("severity"))))
        story.append(_paragraph(f"{str(item.get('severity') or 'medium').upper()} - {item.get('title')}", heading))
        story.append(_paragraph(item.get("reason"), body))
        if item.get("blockers"):
            story.extend(_bullets(_list(item.get("blockers")), small, 5))

    story.append(_paragraph("Safety and integrity", h1))
    story.extend(_bullets([
        "NICO did not modify the assessed repository.",
        "Suggested repairs remain report-only and unverified until exact-context tests pass.",
        "Human approval is required before client delivery.",
        "Unsupported claims permitted: 0.",
        f"Source identity SHA-256: {payload.get('source_identity_sha256')}",
        f"Review packet SHA-256: {_dict(payload.get('review_packet')).get('review_packet_sha256')}",
    ], small, 8))

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.line(document.leftMargin, 0.48 * inch, letter[0] - document.rightMargin, 0.48 * inch)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.3 * inch, "NICO Mid Assessment - evidence-bound - report only - human review required")
        canvas.drawRightString(letter[0] - document.rightMargin, 0.3 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_mid_report_v3() -> dict[str, Any]:
    global _INSTALLED, _ORIGINAL_PAYLOAD
    from nico import mid_assessment_report as report

    if _INSTALLED:
        return {"status": "already_installed", "version": MID_REPORT_V3_VERSION, "pdf_style": PDF_STYLE_VERSION}
    _ORIGINAL_PAYLOAD = report._report_payload
    report._report_payload = build_mid_v3_payload
    report._markdown = decision_ready_markdown
    report._html = decision_ready_html
    report._pdf = decision_ready_pdf
    report.MID_REPORT_VERSION = MID_REPORT_V3_VERSION
    report._nico_mid_report_v3_installed = True
    _INSTALLED = True
    return {
        "status": "installed",
        "version": MID_REPORT_V3_VERSION,
        "pdf_style": PDF_STYLE_VERSION,
        "score_explanation": True,
        "prioritized_repairs": True,
        "consolidated_review": True,
        "report_only": True,
        "human_review_required": True,
        "client_repository_write_allowed": False,
    }


__all__ = [
    "MID_REPORT_V3_VERSION",
    "PDF_STYLE_VERSION",
    "build_mid_v3_payload",
    "decision_ready_html",
    "decision_ready_markdown",
    "decision_ready_pdf",
    "install_mid_report_v3",
]
