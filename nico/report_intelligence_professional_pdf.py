from __future__ import annotations

import base64
import html
import io
import re
import textwrap
from typing import Any, Callable

PDF_STYLE_VERSION = "professional_report_v12_decision_ready"
_PATCH_MARKER = "_nico_professional_report_intelligence_pdf_v2"
_MAX_DETAILED_CANDIDATES = 8
_MAX_SUMMARY_CANDIDATES = 12
_MAX_CODE_CHARS = 4200


def _text(value: Any) -> str:
    text = " ".join(
        str(value or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2022", "-")
        .split()
    )
    text = re.sub(r"\b(max_function_cyclomatic|density)=None\b", r"\1=unavailable", text)
    return text


def _bounded(value: Any, limit: int = 1200) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 4)].rstrip() + "..."


def _paragraph(value: Any, style: Any, limit: int = 1200) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_bounded(value, limit)), style)


def _bullets(items: list[Any], style: Any, *, max_items: int = 8, limit: int = 650) -> list[Any]:
    values = [_text(item) for item in items if _text(item)]
    if not values:
        return []
    flowables: list[Any] = []
    for item in values[:max_items]:
        flowables.append(_paragraph(f"- {item}", style, limit=limit))
    if len(values) > max_items:
        flowables.append(_paragraph(f"- {len(values) - max_items} additional item(s) are retained in the full evidence exports.", style))
    return flowables


def _wrapped_code(value: Any, width: int = 92) -> str:
    raw = html.unescape(str(value or "")).replace("\t", "    ")[:_MAX_CODE_CHARS]
    output: list[str] = []
    for line in raw.splitlines() or [""]:
        indent_count = len(line) - len(line.lstrip(" "))
        indent = " " * min(indent_count, 24)
        content = line.lstrip(" ")
        if not content:
            output.append("")
            continue
        chunks = textwrap.wrap(
            content,
            width=max(24, width - len(indent)),
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [content]
        output.extend(indent + chunk for chunk in chunks)
    if len(str(value or "")) > _MAX_CODE_CHARS:
        output.append("# Additional code omitted; review the full Markdown/HTML report.")
    return "\n".join(output)


def _severity_color(value: Any) -> str:
    severity = str(value or "").lower()
    return {
        "critical": "#991b1b",
        "high": "#dc2626",
        "medium": "#d97706",
        "low": "#2563eb",
        "info": "#64748b",
    }.get(severity, "#64748b")


def _priority_color(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "#64748b"
    if score >= 80:
        return "#991b1b"
    if score >= 60:
        return "#dc2626"
    if score >= 40:
        return "#d97706"
    return "#2563eb"


def _appendix_footer(canvas: Any, doc: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbeafe"))
    canvas.line(doc.leftMargin, 0.52 * inch, doc.pagesize[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 7.3)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 0.33 * inch, "NICO - decision-ready repair intelligence - report only - human review required")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.33 * inch, f"Appendix {doc.page}")
    canvas.restoreState()


def _quality_rows(result: dict[str, Any], p: Callable[..., Any], small: Any, label: Any) -> list[list[Any]]:
    quality = result.get("repository_quality_signals") if isinstance(result.get("repository_quality_signals"), dict) else {}
    groups = quality.get("groups") if isinstance(quality.get("groups"), dict) else {}
    branch = groups.get("branch_hygiene") if isinstance(groups.get("branch_hygiene"), dict) else {}
    frontend = groups.get("frontend_routes") if isinstance(groups.get("frontend_routes"), dict) else {}
    runtime = groups.get("runtime_patch_surface") if isinstance(groups.get("runtime_patch_surface"), dict) else {}
    docs = groups.get("documentation_alignment") if isinstance(groups.get("documentation_alignment"), dict) else {}
    security = groups.get("security_configuration") if isinstance(groups.get("security_configuration"), dict) else {}
    posture = security.get("posture") if isinstance(security.get("posture"), dict) else {}

    security_parts: list[str] = []
    for key, title in (("code_scanning", "Code scanning"), ("secret_scanning", "Secret scanning"), ("dependabot", "Dependabot")):
        item = posture.get(key) if isinstance(posture.get(key), dict) else {}
        status = str(item.get("status") or "unavailable")
        count = item.get("open_alert_count")
        detail = f"{title}: {status}"
        if count is not None:
            detail += f", open={count}"
        security_parts.append(detail)

    values = [
        (
            "Branch governance",
            branch.get("status") or "unavailable",
            f"Inventory={branch.get('branch_count', 'unavailable')} branch(es); truncated={bool(branch.get('truncated'))}.",
        ),
        (
            "Frontend route completeness",
            frontend.get("status") or "unavailable",
            (
                f"Routes={frontend.get('route_count', 0)}; aliases={len(frontend.get('route_aliases') or [])}; "
                f"explicit placeholders={len(frontend.get('explicit_placeholders') or [])}; unread={len(frontend.get('unread_routes') or [])}."
            ),
        ),
        (
            "Runtime patch surface",
            runtime.get("status") or "unavailable",
            (
                f"Patch/compat/fallback modules={runtime.get('patch_compat_fallback_count', 0)}; "
                f"import-time installer calls={runtime.get('package_installer_call_count', 0)}."
            ),
        ),
        (
            "Documentation alignment",
            docs.get("status") or "unavailable",
            (
                f"Documents checked={docs.get('documents_checked', 0)}; missing links={docs.get('missing_link_count', 0)}; "
                f"release claims requiring provider verification={docs.get('release_claim_verification_count', docs.get('stale_release_claim_count', 0))}."
            ),
        ),
        (
            "Provider security configuration",
            security.get("status") or "unavailable",
            "; ".join(security_parts),
        ),
    ]
    rows = [[p("Signal", label), p("Status", label), p("Evidence summary", label)]]
    for name, status, detail in values:
        rows.append([p(name, small), p(str(status).upper(), small), p(detail, small, limit=500)])
    return rows


def _portfolio_rows(repairs: dict[str, Any], p: Callable[..., Any], small: Any, label: Any) -> list[list[Any]]:
    portfolio = repairs.get("portfolio") if isinstance(repairs.get("portfolio"), dict) else {}
    severity = portfolio.get("severity_counts") if isinstance(portfolio.get("severity_counts"), dict) else {}
    effort = portfolio.get("effort_counts") if isinstance(portfolio.get("effort_counts"), dict) else {}
    tgrm = portfolio.get("tgrm_counts") if isinstance(portfolio.get("tgrm_counts"), dict) else {}
    return [
        [p("Portfolio", label), p("Count", label), p("Interpretation", label)],
        [p("Critical / High", small), p(str(int(severity.get("critical", 0)) + int(severity.get("high", 0))), small), p("Immediate containment or bounded structural work.", small)],
        [p("Medium", small), p(str(int(severity.get("medium", 0))), small), p("Plan and verify in the next engineering cycle.", small)],
        [p("Low / Info", small), p(str(int(severity.get("low", 0)) + int(severity.get("info", 0))), small), p("Monitor, batch, or address after higher-value repairs.", small)],
        [p("High effort", small), p(str(int(effort.get("high", 0))), small), p("Requires staged migration or decomposition.", small)],
        [p("TGRM Level 3", small), p(str(int(tgrm.get("level_3", 0))), small), p("Strong containment and full verification required.", small)],
        [p("Code candidates", small), p(str(int(repairs.get("code_suggestion_count") or 0)), small), p("Report-only and unverified until exact-context tests pass.", small)],
        [p("Planning advisories", small), p(str(len(repairs.get("advisories", []) or [])), small), p("Context signals retained outside defect ranking.", small)],
    ]


def _candidate_table(candidates: list[dict[str, Any]], p: Callable[..., Any], small: Any, label: Any) -> Any:
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    rows = [[p("Rank", label), p("Finding", label), p("Severity", label), p("Priority", label), p("Effort", label), p("TGRM", label), p("Code", label)]]
    for item in candidates[:_MAX_SUMMARY_CANDIDATES]:
        tgrm = item.get("tgrm") if isinstance(item.get("tgrm"), dict) else {}
        suggestion = item.get("code_suggestion") if isinstance(item.get("code_suggestion"), dict) else {}
        score = item.get("priority_score")
        score_text = f"{float(score):.1f}" if isinstance(score, (int, float)) else str(score or "N/A")
        rows.append([
            p(f"P{item.get('rank', '?')}", small),
            p(item.get("title") or "Repair candidate", small, limit=250),
            p(str(item.get("severity") or "unknown").upper(), small),
            p(score_text, small),
            p(str(item.get("effort") or "unknown").upper(), small),
            p(f"L{tgrm.get('level', '?')}", small),
            p("Available" if suggestion.get("status") == "available" else "Context", small),
        ])
    table = Table(rows, colWidths=[0.34 * inch, 2.82 * inch, 0.61 * inch, 0.58 * inch, 0.57 * inch, 0.43 * inch, 0.92 * inch], repeatRows=1)
    styles: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for index, item in enumerate(candidates[:_MAX_SUMMARY_CANDIDATES], start=1):
        styles.append(("TEXTCOLOR", (2, index), (2, index), colors.HexColor(_severity_color(item.get("severity")))))
        styles.append(("TEXTCOLOR", (3, index), (3, index), colors.HexColor(_priority_color(item.get("priority_score")))))
    table.setStyle(TableStyle(styles))
    return table


def _build_appendix_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, PageBreak, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.58 * inch,
        leftMargin=0.58 * inch,
        topMargin=0.52 * inch,
        bottomMargin=0.72 * inch,
        title="NICO Decision-Ready Repository Quality and Repair Intelligence",
        author="NICO",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("IntelTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=colors.HexColor("#0f172a"), spaceAfter=7)
    subtitle = ParagraphStyle("IntelSubtitle", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=colors.HexColor("#475569"), spaceAfter=7)
    h2 = ParagraphStyle("IntelH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13.5, leading=16, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5, keepWithNext=True)
    h3 = ParagraphStyle("IntelH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=9.8, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=5, spaceAfter=3, keepWithNext=True)
    body = ParagraphStyle("IntelBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.0, leading=10.3, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("IntelSmall", parent=body, fontSize=7.25, leading=8.9, textColor=colors.HexColor("#475569"), spaceAfter=2)
    label = ParagraphStyle("IntelLabel", parent=small, fontName="Helvetica-Bold", fontSize=7.0, leading=8.4, textColor=colors.HexColor("#475569"), spaceAfter=1)
    callout = ParagraphStyle("IntelCallout", parent=body, fontName="Helvetica-Bold", fontSize=8.0, leading=10.2, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, spaceAfter=8)
    code_style = ParagraphStyle("IntelCode", parent=styles["Code"], fontName="Courier", fontSize=6.6, leading=8.0, textColor=colors.HexColor("#0f172a"), backColor=colors.HexColor("#f8fafc"), borderColor=colors.HexColor("#cbd5e1"), borderWidth=0.5, borderPadding=7, leftIndent=0, rightIndent=0, spaceBefore=3, spaceAfter=6)

    def p(value: Any, style: Any, limit: int = 1200) -> Any:
        return _paragraph(value, style, limit=limit)

    story: list[Any] = [
        p("Decision-Ready Repository Quality and Repair Intelligence", title),
        p(
            "This appendix separates verified defects, engineering risks, and planning advisories. NICO has not changed, committed, pushed, deployed, or opened a pull request against the assessed repository. Suggested code remains unverified until exact-context tests pass and a human approves implementation.",
            callout,
            limit=1500,
        ),
    ]

    quality = result.get("repository_quality_signals") if isinstance(result.get("repository_quality_signals"), dict) else {}
    story.append(p("Repository Quality and Governance Signals", h2))
    summary_table = Table(_quality_rows(result, p, small, label), colWidths=[1.55 * inch, 0.92 * inch, 4.61 * inch], repeatRows=1)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.08 * inch))

    quality_findings = [item for item in quality.get("findings", []) or [] if isinstance(item, dict)]
    if quality_findings:
        story.append(p("Prioritized Quality Findings", h3))
        for finding in quality_findings[:8]:
            severity = str(finding.get("severity") or "unknown").upper()
            heading = f"{severity} - {finding.get('title') or finding.get('code') or 'Quality finding'}"
            heading_style = ParagraphStyle(
                f"Quality{severity}{len(story)}",
                parent=h3,
                textColor=colors.HexColor(_severity_color(severity)),
            )
            block = [p(heading, heading_style)]
            if finding.get("business_impact"):
                block.append(p(f"Business impact: {finding.get('business_impact')}", body, limit=900))
            if finding.get("technical_impact"):
                block.append(p(f"Technical impact: {finding.get('technical_impact')}", small, limit=900))
            if finding.get("recommendation"):
                block.append(p(f"Recommended action: {finding.get('recommendation')}", body, limit=1000))
            block.extend(_bullets(list(finding.get("evidence") or []), small, max_items=4))
            story.extend(block)
            story.append(Spacer(1, 0.03 * inch))
    if quality.get("unavailable"):
        story.append(p("Unavailable or Permission-Limited Evidence", h3))
        story.extend(_bullets(list(quality.get("unavailable") or []), small, max_items=8))

    repairs = result.get("repair_intelligence") if isinstance(result.get("repair_intelligence"), dict) else {}
    candidates = [item for item in repairs.get("candidates", []) or [] if isinstance(item, dict)]
    advisories = [item for item in repairs.get("advisories", []) or [] if isinstance(item, dict)]
    story.append(PageBreak())
    story.append(p("Prioritized Repair Intelligence", h2))
    story.append(p(
        f"Final reconciled repair candidates: {repairs.get('candidate_count', len(candidates))}. Report-only code candidates: {repairs.get('code_suggestion_count', 0)}. Priority uses calibrated severity, exploitability, blast radius, confidence, verification quality, and recurrence; repository size alone is not ranked as a defect.",
        subtitle,
        limit=1200,
    ))

    portfolio_table = Table(_portfolio_rows(repairs, p, small, label), colWidths=[1.35 * inch, 0.55 * inch, 5.18 * inch], repeatRows=1)
    portfolio_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfeff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#155e75")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(portfolio_table)
    story.append(Spacer(1, 0.08 * inch))

    if candidates:
        story.append(_candidate_table(candidates, p, small, label))
        story.append(Spacer(1, 0.10 * inch))

    for item in candidates[:_MAX_DETAILED_CANDIDATES]:
        rank = item.get("rank", "?")
        title_text = item.get("title") or "Repair candidate"
        severity = str(item.get("severity") or "unknown").upper()
        tgrm = item.get("tgrm") if isinstance(item.get("tgrm"), dict) else {}
        score = item.get("priority_score")
        score_text = f"{float(score):.1f}" if isinstance(score, (int, float)) else str(score or "N/A")
        meta = Table([[
            p(f"Severity\n{severity}", label),
            p(f"Priority\n{score_text}", label),
            p(f"Effort\n{str(item.get('effort') or 'unknown').upper()}", label),
            p(f"Confidence\n{item.get('confidence', 'unknown')}", label),
            p(f"TGRM\nLevel {tgrm.get('level', '?')}", label),
        ]], colWidths=[1.05 * inch, 1.05 * inch, 1.05 * inch, 1.35 * inch, 1.35 * inch])
        meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor(_severity_color(severity))),
            ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor(_priority_color(score))),
        ]))
        story.append(KeepTogether([p(f"P{rank} - {title_text}", h3), meta]))
        if item.get("impact"):
            story.append(p(f"Impact: {item.get('impact')}", body, limit=1000))
        if item.get("technical_impact"):
            story.append(p(f"Technical impact: {item.get('technical_impact')}", small, limit=1000))
        if item.get("recommended_action"):
            story.append(p(f"Recommended action: {item.get('recommended_action')}", body, limit=1200))
        if item.get("priority_explanation"):
            story.append(p(f"Why this rank: {item.get('priority_explanation')}", small, limit=900))
        if tgrm.get("scope"):
            story.append(p(f"TGRM scope: {tgrm.get('scope')}", small, limit=800))
        affected = list(item.get("affected_files") or [])
        if affected:
            story.append(p("Affected files or systems", label))
            story.extend(_bullets(affected, small, max_items=10, limit=380))
        evidence = list(item.get("evidence") or [])
        if evidence:
            story.append(p("Evidence", label))
            story.extend(_bullets(evidence, small, max_items=6, limit=520))

        suggestion = item.get("code_suggestion") if isinstance(item.get("code_suggestion"), dict) else {}
        if suggestion.get("status") == "available":
            story.append(p("Suggested replacement code - not applied and not yet verified", h3))
            story.append(p(
                suggestion.get("accuracy_statement") or "This is a review candidate. Validate it against the exact repository context and pass the stated tests before adoption.",
                callout,
                limit=1000,
            ))
            story.append(Preformatted(_wrapped_code(suggestion.get("suggested_code")), code_style, maxLineLength=100))
            conditions = list(suggestion.get("applicability_conditions") or [])
            if conditions:
                story.append(p("Applicability conditions", label))
                story.extend(_bullets(conditions, small, max_items=7, limit=560))
            verification = list(suggestion.get("verification_steps") or [])
            if verification:
                story.append(p("Verification required", label))
                story.extend(_bullets(verification, small, max_items=7, limit=560))
        else:
            story.append(p(
                "Replacement code withheld: the evidence supports a repair plan, but exact file context and tests are required before a conservative code candidate can be produced.",
                small,
                limit=700,
            ))
        if item.get("rollback_plan"):
            story.append(p(f"Rollback: {item.get('rollback_plan')}", small, limit=850))
        story.append(Spacer(1, 0.08 * inch))

    additional = candidates[_MAX_DETAILED_CANDIDATES:_MAX_SUMMARY_CANDIDATES]
    if additional:
        story.append(p("Additional Ranked Items", h3))
        for item in additional:
            story.append(p(
                f"P{item.get('rank', '?')} - {item.get('title')} | priority {item.get('priority_score')} | effort {item.get('effort')} | recommended action: {item.get('recommended_action')}",
                small,
                limit=800,
            ))

    if advisories:
        story.append(p("Planning Advisories - Not Ranked as Defects", h3))
        for item in advisories[:10]:
            story.append(p(f"{item.get('title')}: {item.get('reason')}", small, limit=700))

    doc.build(story, onFirstPage=_appendix_footer, onLaterPages=_appendix_footer)
    return buffer.getvalue()


def build_professional_intelligence_pdf(
    original: Callable[[dict[str, Any]], tuple[str | None, str | None]],
    result: dict[str, Any],
) -> tuple[str | None, str | None]:
    base_pdf, base_error = original(result)
    quality = result.get("repository_quality_signals")
    repairs = result.get("repair_intelligence")
    if not isinstance(quality, dict) and not isinstance(repairs, dict):
        return base_pdf, base_error
    if not base_pdf:
        return None, base_error or "Base professional PDF was unavailable."

    try:
        from pypdf import PdfReader, PdfWriter

        appendix = _build_appendix_pdf(result)
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(base64.b64decode(base_pdf))).pages:
            writer.add_page(page)
        for page in PdfReader(io.BytesIO(appendix)).pages:
            writer.add_page(page)
        metadata = {
            "/Title": "NICO Express Technical Health Assessment",
            "/Author": "NICO",
            "/Subject": "Evidence-bound assessment with calibrated decision-ready repair intelligence",
        }
        writer.add_metadata(metadata)
        output = io.BytesIO()
        writer.write(output)
        portfolio = (repairs or {}).get("portfolio") if isinstance((repairs or {}).get("portfolio"), dict) else {}
        result["report_intelligence_pdf"] = {
            "status": "complete",
            "style": PDF_STYLE_VERSION,
            "structured_appendix": True,
            "decision_ready_portfolio": True,
            "raw_markdown_rendered": False,
            "candidate_count": int((repairs or {}).get("candidate_count") or 0) if isinstance(repairs, dict) else 0,
            "code_suggestion_count": int((repairs or {}).get("code_suggestion_count") or 0) if isinstance(repairs, dict) else 0,
            "advisory_count": len((repairs or {}).get("advisories", []) or []) if isinstance(repairs, dict) else 0,
            "priority_model": str((repairs or {}).get("priority_model") or "unknown") if isinstance(repairs, dict) else "unknown",
            "portfolio": portfolio,
            "report_only": True,
            "human_review_required": True,
            "code_changes_applied": False,
        }
        return base64.b64encode(output.getvalue()).decode("ascii"), None
    except Exception as exc:
        return None, f"Professional report-intelligence PDF appendix failed: {type(exc).__name__}: {exc}"


def install_professional_report_intelligence_pdf() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": PDF_STYLE_VERSION,
            "structured_intelligence_appendix": True,
            "decision_ready_portfolio": True,
        }
    original = current

    def polished_pdf_with_intelligence(result: dict[str, Any]) -> tuple[str | None, str | None]:
        return build_professional_intelligence_pdf(original, result)

    setattr(polished_pdf_with_intelligence, _PATCH_MARKER, True)
    setattr(polished_pdf_with_intelligence, "_nico_previous", original)
    assessment_quality._build_polished_pdf_base64 = polished_pdf_with_intelligence
    assessment_quality.PDF_STYLE_VERSION = PDF_STYLE_VERSION
    return {
        "status": "installed",
        "version": PDF_STYLE_VERSION,
        "structured_intelligence_appendix": True,
        "decision_ready_portfolio": True,
        "raw_markdown_rendered": False,
        "report_only": True,
        "automatic_application_allowed": False,
    }


__all__ = [
    "PDF_STYLE_VERSION",
    "build_professional_intelligence_pdf",
    "install_professional_report_intelligence_pdf",
]
