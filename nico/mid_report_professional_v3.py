from __future__ import annotations

import html
import io
from collections import Counter
from copy import deepcopy
from typing import Any

MID_REPORT_V3_VERSION = "mid-assessment-draft-v3-decision-ready"
_PATCH_MARKER = "_nico_mid_report_professional_v3"
_TECHNICAL_IDS = {
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
}
_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _texts(value: Any) -> list[str]:
    return [" ".join(str(item or "").split()) for item in _list(value) if str(item or "").strip()]


def _score(value: Any) -> int | None:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def _technical_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(payload.get("sections")) if isinstance(item, dict) and item.get("id") in _TECHNICAL_IDS]


def _context_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(payload.get("sections")) if isinstance(item, dict) and item.get("id") not in _TECHNICAL_IDS]


def _weighted_score(sections: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    by_id = {str(item.get("id")): item for item in sections}
    weighted = 0
    total = 0
    rows: list[dict[str, Any]] = []
    for section_id, weight in _WEIGHTS.items():
        section = by_id.get(section_id)
        score = _score(section.get("score")) if section else None
        if score is None:
            continue
        contribution = round(score * weight / 100, 2)
        weighted += score * weight
        total += weight
        rows.append(
            {
                "section_id": section_id,
                "label": section.get("label") or section_id.replace("_", " ").title(),
                "score": score,
                "weight": weight,
                "weighted_contribution": contribution,
                "truth_status": section.get("truth_status") or "Unknown",
            }
        )
    return (round(weighted / total) if total else 0), rows


def _dedupe_exceptions(exceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    category_priority = {
        "critical_or_high_risk_finding": 5,
        "missing_evidence_affecting_delivery": 4,
        "inference_or_external_context": 3,
        "low_confidence_or_limited_conclusion": 2,
        "score_changing_claim": 1,
    }
    for raw in exceptions:
        if not isinstance(raw, dict):
            continue
        section_id = str(raw.get("section_id") or "general")
        blockers = _texts(raw.get("blockers"))
        reason = " ".join(str(raw.get("reason") or "Human review required.").split())
        basis = "|".join(sorted(blockers)) or reason
        key = (section_id, basis.lower())
        item = deepcopy(raw)
        item["blockers"] = blockers
        existing = grouped.get(key)
        if not existing or category_priority.get(str(item.get("category")), 0) > category_priority.get(str(existing.get("category")), 0):
            grouped[key] = item
    return sorted(
        grouped.values(),
        key=lambda item: (
            {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(item.get("severity") or "medium").lower(), 2),
            category_priority.get(str(item.get("category")), 0),
        ),
        reverse=True,
    )


def _score_constraints(rows: list[dict[str, Any]], sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item.get("id")): item for item in sections}
    constraints: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (item["score"], -item["weight"])):
        if row["score"] >= 88:
            continue
        section = by_id.get(str(row["section_id"])) or {}
        findings = _texts(section.get("findings"))
        limitations = _texts(section.get("unavailable")) + _texts(section.get("missing_evidence_sources")) + _texts(section.get("failed_evidence_tools"))
        constraints.append(
            {
                **row,
                "primary_reason": findings[0] if findings else limitations[0] if limitations else "The evidence-supported score is below the stronger-control range.",
                "finding_count": len(findings),
                "limitation_count": len(limitations),
            }
        )
    return constraints[:5]


def _strengths(sections: list[dict[str, Any]]) -> list[str]:
    rows = sorted(
        [item for item in sections if _score(item.get("score")) is not None],
        key=lambda item: _score(item.get("score")) or 0,
        reverse=True,
    )
    values: list[str] = []
    for item in rows:
        score = _score(item.get("score")) or 0
        if score < 80:
            continue
        values.append(f"{item.get('label')}: {score}/100 with truth status {item.get('truth_status') or 'unknown'}.")
    return values[:5]


def _recommended_actions(constraints: list[dict[str, Any]], repair_intelligence: dict[str, Any]) -> list[str]:
    candidates = [item for item in _list(repair_intelligence.get("candidates")) if isinstance(item, dict)]
    actions: list[str] = []
    for item in candidates:
        action = " ".join(str(item.get("recommended_action") or "").split())
        if action and action not in actions:
            actions.append(action)
        if len(actions) >= 4:
            return actions
    for item in constraints:
        action = f"Resolve or disposition the evidence behind {item['label']} ({item['score']}/100): {item['primary_reason']}"
        if action not in actions:
            actions.append(action)
        if len(actions) >= 4:
            break
    return actions


def _enhance_payload(payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    from nico.report_repair_intelligence import build_report_repair_intelligence

    enhanced = deepcopy(payload)
    response = _dict(record.get("response"))
    truth_sections = {
        str(item.get("id")): item
        for item in _list(_dict(response.get("mid_truth_status")).get("sections"))
        if isinstance(item, dict) and item.get("id")
    }
    for section in _list(enhanced.get("sections")):
        if not isinstance(section, dict):
            continue
        truth = truth_sections.get(str(section.get("id"))) or {}
        section["scope_disclosures"] = _texts(truth.get("scope_disclosures"))
        section["confidence"] = truth.get("confidence") or section.get("confidence") or "evidence-bound"
        section["score_evidence_breakdown"] = deepcopy(truth.get("score_evidence_breakdown") or {})

    technical = _technical_sections(enhanced)
    context = _context_sections(enhanced)
    calculated_score, score_rows = _weighted_score(technical)
    assessment = _dict(response.get("assessment"))
    maturity = _dict(assessment.get("maturity_signal"))
    reported_score = _score(maturity.get("score"))
    technical_score = reported_score if reported_score is not None else calculated_score
    maturity_level = str(maturity.get("level") or ("Senior" if technical_score >= 82 else "Mid" if technical_score >= 58 else "Junior"))
    constraints = _score_constraints(score_rows, technical)
    repair_intelligence = build_report_repair_intelligence({"sections": technical})
    exceptions = _dedupe_exceptions([item for item in _list(_dict(enhanced.get("review_packet")).get("exceptions")) if isinstance(item, dict)])
    actions = _recommended_actions(constraints, repair_intelligence)
    coverage = _dict(enhanced.get("evidence_coverage"))

    enhanced.update(
        {
            "report_version": MID_REPORT_V3_VERSION,
            "report_tier": "Mid",
            "detail_level": 3,
            "maturity_signal": {
                "level": maturity_level,
                "score": technical_score,
                "summary": maturity.get("summary") or "Weighted technical maturity is calculated from seven scored technical sections. Human-context modules are unscored and do not lower the technical score.",
            },
            "technical_score": technical_score,
            "score_integrity": {
                "calculated_from_seven_technical_sections": True,
                "weights": deepcopy(_WEIGHTS),
                "weighted_rows": score_rows,
                "calculated_score": calculated_score,
                "reported_score": reported_score,
                "score_match": reported_score is None or reported_score == calculated_score,
                "evidence_coverage_changes_score": False,
                "human_context_sections_change_score_without_review": False,
            },
            "decision_summary": {
                "technical_maturity": maturity_level,
                "technical_score": technical_score,
                "evidence_coverage_percent": coverage.get("percent", 0),
                "verified_strengths": _strengths(technical),
                "primary_score_constraints": constraints,
                "recommended_actions": actions,
                "technical_section_count": len(technical),
                "human_context_section_count": len(context),
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "repair_intelligence": repair_intelligence,
            "deduplicated_review_exceptions": exceptions,
            "review_exception_original_count": len(_list(_dict(enhanced.get("review_packet")).get("exceptions"))),
            "review_exception_final_count": len(exceptions),
        }
    )
    summary = _dict(enhanced.get("executive_summary"))
    summary.update(
        {
            "technical_maturity": maturity_level,
            "technical_score": f"{technical_score}/100",
            "score_basis": "Seven weighted technical sections; five human-context sections remain unscored.",
            "automated_evidence_coverage": f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)})",
            "deduplicated_review_exceptions": len(exceptions),
            "report_tier": "Mid",
            "detail_level": 3,
            "client_delivery": "Human Review Required",
        }
    )
    enhanced["executive_summary"] = summary
    return enhanced


def _markdown(payload: dict[str, Any]) -> str:
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    lines = [
        "# NICO MID ASSESSMENT",
        "",
        "**DRAFT — HUMAN REVIEW REQUIRED**",
        "",
        f"- Report ID: `{payload.get('report_id')}`",
        f"- Mid run ID: `{payload.get('run_id')}`",
        f"- Repository: `{payload.get('repository')}`",
        f"- Snapshot commit: `{payload.get('snapshot_commit_sha')}`",
        f"- Generated: {payload.get('generated_at')}",
        "",
        "## Decision summary",
        "",
        f"- Technical maturity: **{decision.get('technical_maturity')}**",
        f"- Technical score: **{decision.get('technical_score')}/100**",
        f"- Automated evidence coverage: **{decision.get('evidence_coverage_percent')}%**",
        f"- Technical sections scored: {decision.get('technical_section_count')}",
        f"- Human-context sections unscored: {decision.get('human_context_section_count')}",
        "- Client delivery: **Human review required**",
        "",
        "### Why this score",
        "",
        "The score is the weighted result of seven technical sections. Evidence coverage and unscored stakeholder/context modules do not directly raise or lower it.",
    ]
    for row in integrity.get("weighted_rows") or []:
        lines.append(f"- {row.get('label')}: {row.get('score')}/100 × {row.get('weight')}% = {row.get('weighted_contribution')} weighted points")
    lines.extend(["", "### Primary score constraints", ""])
    for item in decision.get("primary_score_constraints") or []:
        lines.append(f"- **{item.get('label')} — {item.get('score')}/100:** {item.get('primary_reason')}")
    lines.extend(["", "### Recommended actions", ""])
    for item in decision.get("recommended_actions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Technical scorecard", ""])
    for section in _technical_sections(payload):
        lines.append(f"### {section.get('label')} — {section.get('score')}/100")
        lines.append("")
        lines.append(f"- Truth status: **{section.get('truth_status')}**")
        lines.append(f"- Summary: {section.get('summary')}")
        if section.get("findings"):
            lines.append("- Findings:")
            lines.extend(f"  - {item}" for item in _texts(section.get("findings")))
        if section.get("unavailable") or section.get("missing_evidence_sources") or section.get("failed_evidence_tools"):
            lines.append("- Material limitations:")
            lines.extend(f"  - {item}" for item in (_texts(section.get("unavailable")) + _texts(section.get("missing_evidence_sources")) + _texts(section.get("failed_evidence_tools"))))
        if section.get("scope_disclosures"):
            lines.append("- Scope disclosures:")
            lines.extend(f"  - {item}" for item in _texts(section.get("scope_disclosures")))
        lines.append("")
    lines.extend(["## Prioritized repair intelligence", ""])
    for candidate in _list(_dict(payload.get("repair_intelligence")).get("candidates"))[:10]:
        if not isinstance(candidate, dict):
            continue
        lines.append(f"### P{candidate.get('rank', '?')} — {candidate.get('title')}")
        lines.append(f"- Severity: {candidate.get('severity')} | Priority: {candidate.get('priority_score')} | Effort: {candidate.get('effort')}")
        lines.append(f"- Action: {candidate.get('recommended_action')}")
        lines.append("")
    context = _context_sections(payload)
    if context:
        lines.extend(["## Human-context modules", ""])
        for section in context:
            lines.append(f"- **{section.get('label')} — {section.get('truth_status')}:** {section.get('summary')}")
    lines.extend(["", "## Review by exception", ""])
    for item in payload.get("deduplicated_review_exceptions") or []:
        lines.append(f"- **{item.get('title') or item.get('category')}** ({item.get('severity') or 'medium'}): {item.get('reason')}")
        for blocker in _texts(item.get("blockers")):
            lines.append(f"  - {blocker}")
    lines.extend([
        "",
        "## Integrity identity",
        "",
        f"- Source identity SHA-256: `{payload.get('source_identity_sha256')}`",
        f"- Review packet SHA-256: `{_dict(payload.get('review_packet')).get('review_packet_sha256')}`",
        f"- Snapshot commit SHA: `{payload.get('snapshot_commit_sha')}`",
        "",
        "NICO did not modify the assessed repository. Suggested repairs remain report-only, unverified, and human-review-bound.",
    ])
    return "\n".join(lines).strip() + "\n"


def _html(payload: dict[str, Any]) -> str:
    markdown = _markdown(payload)
    escaped = html.escape(markdown)
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>NICO Mid Assessment</title><style>
body{{font-family:Inter,Arial,sans-serif;max-width:1080px;margin:32px auto;padding:0 24px;color:#172033;line-height:1.55;background:#f8fafc}}pre{{white-space:pre-wrap;background:white;border:1px solid #cbd5e1;border-radius:14px;padding:24px;box-shadow:0 12px 30px rgba(15,23,42,.08)}}
</style></head><body><pre>{escaped}</pre></body></html>"""


def _pdf(payload: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.68 * inch,
        title="NICO Mid Technical Assessment",
        author="NICO",
    )
    styles = getSampleStyleSheet()
    hero = ParagraphStyle("MidHero", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=31, textColor=colors.white, alignment=1)
    hero_sub = ParagraphStyle("MidHeroSub", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#67e8f9"), alignment=1)
    h2 = ParagraphStyle("MidH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13.2, leading=16, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5, keepWithNext=True)
    h3 = ParagraphStyle("MidH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.8, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=5, spaceAfter=3, keepWithNext=True)
    body = ParagraphStyle("MidBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.5, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("MidSmall", parent=body, fontSize=7.3, leading=9.1, textColor=colors.HexColor("#475569"), spaceAfter=2)
    label = ParagraphStyle("MidLabel", parent=small, fontName="Helvetica-Bold", fontSize=7, textColor=colors.HexColor("#64748b"))
    callout = ParagraphStyle("MidCallout", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, spaceAfter=7)
    warn = ParagraphStyle("MidWarn", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#854d0e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=0.7, borderPadding=7, spaceAfter=7)

    def p(value: Any, style: Any, limit: int = 1200) -> Paragraph:
        text = " ".join(str(value or "").split())
        if len(text) > limit:
            text = text[: limit - 3].rstrip() + "..."
        return Paragraph(html.escape(text), style)

    def bullets(values: Any, max_items: int = 6) -> list[Any]:
        items = _texts(values)
        rows = [p(f"- {item}", small, 650) for item in items[:max_items]]
        if len(items) > max_items:
            rows.append(p(f"- {len(items) - max_items} additional item(s) retained in Markdown/JSON evidence.", small))
        return rows

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbeafe"))
        canvas.line(document.leftMargin, 0.49 * inch, document.pagesize[0] - document.rightMargin, 0.49 * inch)
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.31 * inch, "NICO Mid - snapshot-bound - evidence-bound - human review required")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.31 * inch, f"Page {document.page}")
        canvas.restoreState()

    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    coverage = _dict(payload.get("evidence_coverage"))
    technical = _technical_sections(payload)
    context = _context_sections(payload)

    hero_table = Table(
        [[p("NICO", hero)], [p("POWERED BY REPARODYNAMICS", hero_sub)], [p("MID TECHNICAL ASSESSMENT", hero_sub)]],
        colWidths=[7.12 * inch],
    )
    hero_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    metadata = Table(
        [
            [p("Repository", label), p(payload.get("repository"), small), p("Client", label), p(payload.get("client_name") or "Not provided", small)],
            [p("Snapshot", label), p(str(payload.get("snapshot_commit_sha") or "")[:16], small), p("Run", label), p(payload.get("run_id"), small)],
        ],
        colWidths=[0.82 * inch, 2.72 * inch, 0.68 * inch, 2.9 * inch],
    )
    metadata.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    metrics = Table(
        [[
            [p("MATURITY", label), p(decision.get("technical_maturity"), h3)],
            [p("TECHNICAL SCORE", label), p(f"{decision.get('technical_score')}/100", h3)],
            [p("EVIDENCE COVERAGE", label), p(f"{coverage.get('percent', 0)}%", h3)],
            [p("DELIVERY", label), p("HUMAN REVIEW", h3)],
        ]],
        colWidths=[1.65 * inch, 1.65 * inch, 1.65 * inch, 2.17 * inch],
    )
    metrics.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story: list[Any] = [
        hero_table,
        Spacer(1, 0.08 * inch),
        metadata,
        Spacer(1, 0.08 * inch),
        metrics,
        Spacer(1, 0.08 * inch),
        p("DRAFT — automated technical work is complete, but approval and client delivery require human review of this exact snapshot-bound artifact.", warn),
        p("Decision Summary", h2),
        p("The technical score is calculated from seven weighted technical sections. The five stakeholder and product-context modules are unscored and do not lower the score. Evidence coverage measures availability, not maturity.", callout, 1400),
    ]

    if decision.get("verified_strengths"):
        story.append(p("Verified strengths", h3))
        story.extend(bullets(decision.get("verified_strengths"), 5))
    if decision.get("primary_score_constraints"):
        story.append(p("Primary score constraints", h3))
        for item in decision.get("primary_score_constraints")[:5]:
            story.append(p(f"{item.get('label')} - {item.get('score')}/100: {item.get('primary_reason')}", body, 900))
    if decision.get("recommended_actions"):
        story.append(p("Recommended actions", h3))
        story.extend(bullets(decision.get("recommended_actions"), 5))

    story.append(p("Weighted Technical Scorecard", h2))
    score_rows = [[p("Area", label), p("Truth", label), p("Score", label), p("Weight", label), p("Contribution", label)]]
    for row in integrity.get("weighted_rows") or []:
        score_rows.append([
            p(row.get("label"), small),
            p(row.get("truth_status"), small),
            p(str(row.get("score")), small),
            p(f"{row.get('weight')}%", small),
            p(str(row.get("weighted_contribution")), small),
        ])
    score_table = Table(score_rows, colWidths=[2.18 * inch, 1.72 * inch, 0.55 * inch, 0.58 * inch, 0.87 * inch], repeatRows=1)
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(score_table)
    story.append(p(f"Calculated score={integrity.get('calculated_score')}; reported score={integrity.get('reported_score')}; match={integrity.get('score_match')}. Human-context modules and coverage percentage do not directly change this score.", small))

    story.append(PageBreak())
    story.append(p("Technical Findings and Evidence", h2))
    for section in technical:
        section_score = _score(section.get("score"))
        block = [
            p(f"{section.get('label')} - {section_score if section_score is not None else 'Not scored'}/100", h3),
            p(f"Truth status: {section.get('truth_status')} | Confidence: {section.get('confidence') or 'evidence-bound'}", small),
            p(section.get("summary"), body, 900),
        ]
        story.extend(KeepTogether(block))
        if section.get("findings"):
            story.append(p("Findings", label))
            story.extend(bullets(section.get("findings"), 5))
        limitations = _texts(section.get("unavailable")) + _texts(section.get("missing_evidence_sources")) + _texts(section.get("failed_evidence_tools"))
        if limitations:
            story.append(p("Material limitations", label))
            story.extend(bullets(limitations, 5))
        if section.get("scope_disclosures"):
            story.append(p("Scope disclosures", label))
            story.extend(bullets(section.get("scope_disclosures"), 3))
        story.append(Spacer(1, 0.06 * inch))

    repairs = _dict(payload.get("repair_intelligence"))
    candidates = [item for item in _list(repairs.get("candidates")) if isinstance(item, dict)]
    if candidates:
        story.append(PageBreak())
        story.append(p("Prioritized Repair Intelligence", h2))
        story.append(p("Repairs are report-only candidates. NICO did not change the assessed repository, create a branch, commit, pull request, or deployment.", callout))
        repair_rows = [[p("Rank", label), p("Finding", label), p("Severity", label), p("Priority", label), p("Effort", label)]]
        for item in candidates[:10]:
            repair_rows.append([
                p(f"P{item.get('rank', '?')}", small),
                p(item.get("title"), small, 260),
                p(str(item.get("severity") or "unknown").upper(), small),
                p(str(item.get("priority_score") or "N/A"), small),
                p(str(item.get("effort") or "unknown").upper(), small),
            ])
        repair_table = Table(repair_rows, colWidths=[0.42 * inch, 3.92 * inch, 0.78 * inch, 0.72 * inch, 0.72 * inch], repeatRows=1)
        repair_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfeff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#155e75")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(repair_table)
        for item in candidates[:6]:
            story.append(p(f"P{item.get('rank', '?')} - {item.get('title')}", h3))
            story.append(p(f"Recommended action: {item.get('recommended_action')}", body, 1000))
            story.append(p(f"Verification: {'; '.join(_texts(item.get('test_plan')))}", small, 800))

    if context:
        story.append(p("Human-Context Modules", h2))
        story.append(p("These modules are valuable for a Mid assessment but remain unscored until submitted context is validated by a human reviewer.", callout))
        context_rows = [[p("Module", label), p("Status", label), p("Submitted evidence / next step", label)]]
        for section in context:
            evidence = "; ".join(_texts(section.get("evidence"))) or "No validated external context attached."
            context_rows.append([p(section.get("label"), small), p(section.get("truth_status"), small), p(evidence, small, 500)])
        context_table = Table(context_rows, colWidths=[1.6 * inch, 1.35 * inch, 4.17 * inch], repeatRows=1)
        context_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(context_table)

    story.append(p("Review by Exception", h2))
    story.append(p(f"Original exception records: {payload.get('review_exception_original_count', 0)}. Decision-ready deduplicated items: {payload.get('review_exception_final_count', 0)}.", small))
    for item in payload.get("deduplicated_review_exceptions") or []:
        story.append(p(f"{str(item.get('severity') or 'medium').upper()} - {item.get('title') or item.get('category')}", h3))
        story.append(p(item.get("reason"), body, 800))
        story.extend(bullets(item.get("blockers"), 5))

    story.append(p("Integrity and Safety Boundary", h2))
    story.extend(bullets([
        f"Source identity SHA-256: {payload.get('source_identity_sha256')}",
        f"Review packet SHA-256: {_dict(payload.get('review_packet')).get('review_packet_sha256')}",
        f"Snapshot commit SHA: {payload.get('snapshot_commit_sha')}",
        "Human review is required before approval or client delivery.",
        "NICO did not modify the assessed repository and cannot automatically apply report suggestions.",
    ], 8))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def install_mid_report_professional_v3() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_V3_VERSION}
    original_payload = report_module._report_payload

    def payload_v3(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return _enhance_payload(original_payload(record, packet, identity, generated_at), record)

    report_module._report_payload = payload_v3
    report_module._markdown = _markdown
    report_module._html = _html
    report_module._pdf = _pdf
    report_module.MID_REPORT_VERSION = MID_REPORT_V3_VERSION
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": MID_REPORT_V3_VERSION,
        "decision_summary": True,
        "weighted_score_explanation": True,
        "deduplicated_review_exceptions": True,
        "prioritized_repair_intelligence": True,
        "report_only": True,
        "human_review_required": True,
    }


__all__ = [
    "MID_REPORT_V3_VERSION",
    "install_mid_report_professional_v3",
]
