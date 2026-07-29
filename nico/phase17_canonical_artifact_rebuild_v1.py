from __future__ import annotations

import base64
import hashlib
import html
import io
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.v2.canonical-artifact-renderer.v2"


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _list(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(dict(item)) for item in (value or []) if isinstance(item, Mapping)]


def _score_truth(canonical: Mapping[str, Any]) -> tuple[Any, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    technical = assessment.get(
        "technical_score",
        maturity.get("technical_score", maturity.get("presented_score", maturity.get("score"))),
    )
    adjusted = assessment.get(
        "canonical_evidence_adjusted_score",
        assessment.get("evidence_adjusted_score", maturity.get("canonical_evidence_adjusted_score", technical)),
    )
    return technical, adjusted


def _scanner_rows(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = _list(canonical.get("scanner_execution_records"))
    if records:
        return records
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    return _list(assessment.get("scanner_execution_records"))


def _criterion_lines(finding: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in finding.get("acceptance_criteria") or []:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _markdown(canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    findings = _list(canonical.get("canonical_findings") or canonical.get("findings_register"))
    sections = _list(assessment.get("sections"))
    scanners = _scanner_rows(canonical)
    roadmap = _list(canonical.get("roadmap"))
    technical, adjusted = _score_truth(canonical)

    lines = [
        "# NICO Comprehensive Technical Assessment",
        "",
        "**FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED**",
        "",
        f"- Repository: {_text(identity.get('repository'))}",
        f"- Exact commit: {_text(identity.get('commit_sha'))}",
        f"- Run ID: {_text(identity.get('run_id'))}",
        f"- Technical maturity: {technical}/100" if isinstance(technical, (int, float)) else "- Technical maturity: Not scored",
        f"- Evidence-Adjusted: {adjusted}/100" if isinstance(adjusted, (int, float)) else "- Evidence-Adjusted: Not scored",
        "- Assessment package: Complete",
        "- Internal review: Required",
        "- Client-ready: No · Internal approval required",
        "",
        "## Executive decision brief",
        "",
        _text(assessment.get("executive_summary") or "The automated assessment completed and remains subject to internal review."),
        "",
        "## Technical scorecard",
        "",
        "| Control | Score | Assurance |",
        "|---|---:|---|",
    ]
    for section in sections:
        score = section.get("score_value", section.get("presented_score", section.get("score")))
        assurance = _text(
            section.get("assurance_label")
            or section.get("assurance_status")
            or section.get("presented_status")
            or section.get("status")
        )
        lines.append(
            f"| {_text(section.get('label') or section.get('id'))} | "
            f"{score if isinstance(score, (int, float)) else 'Not scored'} | {assurance} |"
        )
    if not sections:
        lines.append("| Canonical scoring | Not scored | Review required |")

    lines += ["", "## Evidence health", ""]
    if scanners:
        lines += [
            "| Scanner | State | Exact commit | Artifact | Findings | Reason |",
            "|---|---|---|---|---:|---|",
        ]
        for scanner in scanners:
            state = _text(scanner.get("state") or scanner.get("status") or "unknown")
            exact = scanner.get("exact_commit_match") is True or _text(scanner.get("commit_sha")) == _text(identity.get("commit_sha"))
            artifact = _text(scanner.get("artifact_hash"))
            reason = _text(scanner.get("failure_reason") or scanner.get("reason"), 500)
            lines.append(
                f"| {_text(scanner.get('scanner_name') or scanner.get('tool'))} | {state} | "
                f"{'Yes' if exact else 'No'} | {'Retained' if artifact else 'Missing'} | "
                f"{len(scanner.get('findings') or [])} | {reason or '—'} |"
            )
    else:
        lines.append("- No normalized scanner records were retained in the canonical package.")

    lines += ["", "## Canonical findings", ""]
    if not findings:
        lines.append("No canonical actionable finding was retained.")
    for finding in findings:
        identifier = _text(finding.get("finding_id") or finding.get("id"))
        title = _text(finding.get("title") or finding.get("decision_title"))
        lines += [
            f"### {_text(finding.get('priority') or 'P2')} · {title} · {identifier}",
            "",
            f"- Category / status: {_text(finding.get('category'))} · {_text(finding.get('status'))}",
            f"- Location: {_text(finding.get('location')) or 'Location not retained'}",
            f"- Evidence: {_text(finding.get('fact') or finding.get('evidence'))}",
            f"- Interpretation: {_text(finding.get('interpretation') or title)}",
            f"- Business impact: {_text(finding.get('business_impact') or finding.get('impact'))}",
            f"- Recommendation: {_text(finding.get('recommendation'))}",
            f"- Owner / effort: {_text(finding.get('owner_role'))} · {_text(finding.get('effort'))}",
            f"- Cost of inaction: {_text(finding.get('cost_of_inaction')) or 'Not quantified'}",
            f"- Residual risk: {_text(finding.get('residual_risk')) or 'Requires review'}",
        ]
        criteria = _criterion_lines(finding)
        if criteria:
            lines.append("- Acceptance criteria:")
            lines.extend(f"  - {value}" for value in criteria)
        aliases = [_text(value) for value in finding.get("finding_aliases") or [] if _text(value)]
        if aliases:
            lines.append(f"- Historical aliases: {', '.join(dict.fromkeys(aliases))}")
        lines.append("")

    if roadmap:
        lines += ["## Six-month roadmap", ""]
        for window in roadmap:
            lines.append(f"### {_text(window.get('window') or window.get('title'))}")
            if _text(window.get("objective")):
                lines.append(_text(window.get("objective")))
            packages = _list(window.get("work_packages"))
            if packages:
                for work in packages:
                    lines.append(
                        f"- {_text(work.get('work_package_id') or work.get('id'))}: "
                        f"{_text(work.get('title') or work.get('objective'))} · "
                        f"owner {_text(work.get('owner_role') or work.get('owner'))} · "
                        f"effort {_text(work.get('effort') or work.get('effort_range'))}"
                    )
            lines.append("")

    limitations = [
        _text(value)
        for value in assessment.get("unavailable_data_notes") or []
        if _text(value)
    ]
    lines += ["## Evidence limitations", ""]
    lines.extend(f"- {value}" for value in dict.fromkeys(limitations))
    if not limitations:
        lines.append("- No assessment-wide limitation was recorded beyond finding and scanner-level disclosures.")

    lines += [
        "",
        "## Review and delivery gate",
        "",
        "The automated assessment package is complete. An authorized reviewer must inspect and approve the exact immutable package before client delivery.",
        "",
        "**PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED**",
    ]
    return "\n".join(lines).strip() + "\n"


def _html(markdown: str) -> str:
    blocks: list[str] = []
    list_items: list[str] = []
    table_lines: list[str] = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []

    def flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        rows = []
        for index, line in enumerate(table_lines):
            cells = [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            if index == 1 and all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            tag = "th" if index == 0 else "td"
            rows.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
        blocks.append("<div class=\"table-wrap\"><table>" + "".join(rows) + "</table></div>")
        table_lines = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            flush_list()
            table_lines.append(line)
            continue
        flush_table()
        if not line:
            flush_list()
        elif line.startswith("### "):
            flush_list(); blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_list(); blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_list(); blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("  - "):
            list_items.append(f"<li>{html.escape(line[4:])}</li>")
        elif line.startswith("- "):
            list_items.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            flush_list(); blocks.append(f"<p class=\"warning\">{html.escape(line.strip('*'))}</p>")
        else:
            flush_list(); blocks.append(f"<p>{html.escape(line)}</p>")
    flush_list(); flush_table()
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NICO Comprehensive Technical Assessment</title><style>
body{margin:0;background:#071124;color:#dbeafe;font:15px/1.55 Inter,system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:32px 20px 72px}article{background:#0b172c;border:1px solid #274060;border-radius:22px;padding:28px}h1{font-size:42px;line-height:1.05;color:#fff}h2{color:#7dd3fc;border-top:1px solid #274060;padding-top:24px;margin-top:34px}h3{color:#e0f2fe}p,li{color:#cbd5e1}.warning{padding:14px;border:1px solid #f59e0b;border-radius:12px;background:#4a2406;color:#fde68a;font-weight:800}.table-wrap{overflow:auto;margin:16px 0}table{width:100%;border-collapse:collapse;background:#0d1a31}th,td{border:1px solid #274060;padding:9px;text-align:left;vertical-align:top}th{color:#fff;background:#0c4a6e}
</style></head><body><main><article>""" + "".join(blocks) + "</article></main></body></html>"


def _pdf(canonical: Mapping[str, Any], markdown: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    technical, adjusted = _score_truth(canonical)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("V2Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor("#0f172a"))
    h1 = ParagraphStyle("V2H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#075985"), spaceBefore=12, spaceAfter=7)
    h2 = ParagraphStyle("V2H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("V2Body", parent=styles["BodyText"], fontSize=8.3, leading=11.2, textColor=colors.HexColor("#334155"), spaceAfter=4)
    bullet = ParagraphStyle("V2Bullet", parent=body, leftIndent=12, firstLineIndent=-7)
    warning = ParagraphStyle("V2Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=8, spaceAfter=10)

    def paragraph(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 50)} · FINAL · PENDING APPROVAL")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Page {doc.page}")
        canvas.restoreState()

    story: list[Any] = [
        Spacer(1, .45 * inch),
        paragraph("NICO COMPREHENSIVE", title),
        paragraph("Decision-Grade Technical Assessment", h1),
        paragraph("FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED", warning),
        Spacer(1, .1 * inch),
    ]
    score_rows = [
        ["Repository", _text(identity.get("repository"))],
        ["Exact commit", _text(identity.get("commit_sha"))],
        ["Run ID", _text(identity.get("run_id"))],
        ["Technical maturity", f"{technical}/100" if isinstance(technical, (int, float)) else "Not scored"],
        ["Evidence-Adjusted", f"{adjusted}/100" if isinstance(adjusted, (int, float)) else "Not scored"],
        ["Internal review", "Required"],
        ["Client-ready", "No"],
    ]
    score_table = Table(score_rows, colWidths=[1.45 * inch, 5.35 * inch])
    score_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [score_table, PageBreak()]

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith("# NICO") or line.startswith("|") or set(line) <= {"|", "-", ":"}:
            continue
        if line.startswith("## "):
            story += [PageBreak(), paragraph(line[3:], h1)]
        elif line.startswith("### "):
            story.append(paragraph(line[4:], h2))
        elif line.startswith("  - "):
            story.append(paragraph("• " + line[4:], bullet))
        elif line.startswith("- "):
            story.append(paragraph("• " + line[2:], bullet))
        elif line.startswith("**") and line.endswith("**"):
            story.append(paragraph(line.strip("*"), warning))
        else:
            story.append(paragraph(line, body))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        title="NICO Comprehensive Technical Assessment",
        author="NICO",
        invariant=1,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {})) if isinstance(result.get("json"), Mapping) else {}
    canonical.update({
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment_state": "review_required",
    })
    markdown = _markdown(canonical)
    rendered_html = _html(markdown)
    pdf = _pdf(canonical, markdown)
    result.update({
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "markdown_available": True,
        "html_available": True,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_available": True,
        "pdf_error": None,
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment_state": "review_required",
    })
    result["canonical_truth_sha256"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    result["phase17_artifact_rebuild"] = {
        "version": VERSION,
        "rebuilt_from_repaired_canonical_truth": True,
        "markdown_html_pdf_share_one_canonical_population": True,
        "markdown_embedded_for_direct_user_gesture_copy": True,
        "pdf_signature_verified": pdf.startswith(b"%PDF"),
        "canonical_finding_count": len(canonical.get("canonical_findings") or []),
        "scanner_record_count": len(canonical.get("scanner_execution_records") or []),
        "finality_semantics_embedded": True,
    }
    return result


__all__ = ["VERSION", "rebuild_client_artifacts"]
