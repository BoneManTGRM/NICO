from __future__ import annotations

import base64
import hashlib
import html
import io
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.phase17.canonical-artifact-rebuild.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _list(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(dict(item)) for item in (value or []) if isinstance(item, Mapping)]


def _markdown(canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    findings = _list(canonical.get("canonical_findings") or canonical.get("findings_register"))
    sections = _list(assessment.get("sections"))
    roadmap = _list(canonical.get("roadmap"))
    technical = assessment.get("technical_score", maturity.get("technical_score", maturity.get("score")))
    adjusted = assessment.get("canonical_evidence_adjusted_score", assessment.get("evidence_adjusted_score"))

    lines = [
        "# NICO Comprehensive Technical Assessment",
        "",
        f"- Repository: {_text(identity.get('repository'))}",
        f"- Exact commit: {_text(identity.get('commit_sha'))}",
        f"- Run ID: {_text(identity.get('run_id'))}",
        f"- Technical maturity: {technical}/100" if isinstance(technical, (int, float)) else "- Technical maturity: Not scored",
        f"- Evidence-adjusted: {adjusted}/100" if isinstance(adjusted, (int, float)) else "- Evidence-adjusted: Not scored",
        "- Assessment package: Complete",
        "- Internal review: Required",
        "- Client-ready: No - internal approval required",
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
        lines.append(f"| {_text(section.get('label') or section.get('id'))} | {score if isinstance(score, (int, float)) else 'Not scored'} | {_text(section.get('assurance_label') or section.get('assurance_status') or section.get('status'))} |")

    lines += ["", "## Canonical findings", ""]
    for finding in findings:
        lines += [
            f"### {_text(finding.get('priority') or 'P2')} - {_text(finding.get('title') or finding.get('decision_title'))} - {_text(finding.get('finding_id') or finding.get('id'))}",
            "",
            f"- Category / status: {_text(finding.get('category'))} / {_text(finding.get('status'))}",
            f"- Location: {_text(finding.get('location')) or 'Location not retained'}",
            f"- Evidence: {_text(finding.get('fact') or finding.get('evidence'))}",
            f"- Interpretation: {_text(finding.get('interpretation'))}",
            f"- Business impact: {_text(finding.get('business_impact') or finding.get('impact'))}",
            f"- Recommendation: {_text(finding.get('recommendation'))}",
            f"- Owner / effort: {_text(finding.get('owner_role'))} / {_text(finding.get('effort'))}",
            f"- Cost of inaction: {_text(finding.get('cost_of_inaction'))}",
            f"- Residual risk: {_text(finding.get('residual_risk'))}",
        ]
        criteria = [_text(value) for value in finding.get("acceptance_criteria") or [] if _text(value)]
        if criteria:
            lines.append("- Acceptance criteria:")
            lines.extend(f"  - {value}" for value in criteria)
        lines.append("")

    if roadmap:
        lines += ["## Six-month roadmap", ""]
        for window in roadmap:
            lines.append(f"### {_text(window.get('window') or window.get('title'))}")
            if _text(window.get("objective")):
                lines.append(_text(window.get("objective")))
            for package in _list(window.get("work_packages")):
                lines.append(f"- {_text(package.get('work_package_id') or package.get('id'))}: {_text(package.get('title') or package.get('objective'))} - owner {_text(package.get('owner_role') or package.get('owner'))}, effort {_text(package.get('effort') or package.get('effort_range'))}")
            lines.append("")

    lines += [
        "## Review and delivery gate",
        "",
        "The automated assessment package is complete. An authorized reviewer must approve the exact immutable package before client delivery.",
    ]
    return "\n".join(lines).strip() + "\n"


def _pdf(canonical: Mapping[str, Any], markdown: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Phase17Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor("#0f172a"))
    h1 = ParagraphStyle("Phase17H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#075985"), spaceBefore=12, spaceAfter=7)
    h2 = ParagraphStyle("Phase17H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Phase17Body", parent=styles["BodyText"], fontSize=8.5, leading=11.5, textColor=colors.HexColor("#334155"), spaceAfter=4)
    bullet = ParagraphStyle("Phase17Bullet", parent=body, leftIndent=12, firstLineIndent=-7)

    story: list[Any] = [Spacer(1, .35 * inch), Paragraph("NICO COMPREHENSIVE", title), Paragraph("Decision-Grade Technical Assessment", h1)]
    for raw in markdown.splitlines()[2:]:
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 3))
        elif line.startswith("## "):
            story += [PageBreak(), Paragraph(html.escape(line[3:]), h1)]
        elif line.startswith("### "):
            story.append(Paragraph(html.escape(line[4:]), h2))
        elif line.startswith("- "):
            story.append(Paragraph("- " + html.escape(line[2:]), bullet))
        elif line.startswith("  - "):
            story.append(Paragraph("- " + html.escape(line[4:]), bullet))
        elif line.startswith("|"):
            continue
        else:
            story.append(Paragraph(html.escape(line), body))
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.55 * inch, title="NICO Comprehensive Technical Assessment", author="NICO", invariant=1)
    doc.build(story)
    return buffer.getvalue()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {})) if isinstance(result.get("json"), Mapping) else {}
    markdown = _markdown(canonical)
    pdf = _pdf(canonical, markdown)
    result["markdown"] = markdown
    result["markdown_available"] = True
    result["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    result["pdf_base64"] = base64.b64encode(pdf).decode("ascii")
    result["pdf_available"] = True
    result["pdf_error"] = None
    result["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
    result["canonical_truth_sha256"] = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    result["phase17_artifact_rebuild"] = {
        "version": VERSION,
        "rebuilt_from_repaired_canonical_truth": True,
        "markdown_embedded_for_direct_user_gesture_copy": True,
        "pdf_signature_verified": pdf.startswith(b"%PDF"),
        "canonical_finding_count": len(canonical.get("canonical_findings") or []),
    }
    return result


__all__ = ["VERSION", "rebuild_client_artifacts"]
