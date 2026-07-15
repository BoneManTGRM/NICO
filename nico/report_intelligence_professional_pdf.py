from __future__ import annotations

import base64
import html
import io
import textwrap
from typing import Any, Callable

PDF_STYLE_VERSION = "professional_report_v11_intelligence"
_PATCH_MARKER = "_nico_professional_report_intelligence_pdf_v1"
_MAX_DETAILED_CANDIDATES = 15
_MAX_CODE_CHARS = 4800


def _text(value: Any) -> str:
    return " ".join(
        str(value or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2022", "-")
        .split()
    )


def _bounded(value: Any, limit: int = 1200) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 18)].rstrip() + "... [truncated]"


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
        flowables.append(_paragraph(f"- {len(values) - max_items} additional item(s) are available in the Markdown/HTML report.", style))
    return flowables


def _wrapped_code(value: Any, width: int = 96) -> str:
    raw = str(value or "").replace("\t", "    ")[:_MAX_CODE_CHARS]
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
        "critical": "#b91c1c",
        "high": "#dc2626",
        "medium": "#d97706",
        "low": "#2563eb",
        "info": "#64748b",
    }.get(severity, "#64748b")


def _appendix_footer(canvas: Any, doc: Any) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#dbeafe"))
    canvas.line(doc.leftMargin, 0.52 * inch, doc.pagesize[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 7.3)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(doc.leftMargin, 0.33 * inch, "NICO - structured repair-intelligence appendix - report only - human review required")
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
        title="NICO Repository Quality and Repair Intelligence",
        author="NICO",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("IntelTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#0f172a"), spaceAfter=8)
    subtitle = ParagraphStyle("IntelSubtitle", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#475569"), spaceAfter=8)
    h2 = ParagraphStyle("IntelH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=5, keepWithNext=True)
    h3 = ParagraphStyle("IntelH3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=5, spaceAfter=3, keepWithNext=True)
    body = ParagraphStyle("IntelBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.6, textColor=colors.HexColor("#334155"), spaceAfter=3)
    small = ParagraphStyle("IntelSmall", parent=body, fontSize=7.4, leading=9.1, textColor=colors.HexColor("#475569"), spaceAfter=2)
    label = ParagraphStyle("IntelLabel", parent=small, fontName="Helvetica-Bold", fontSize=7.1, leading=8.5, textColor=colors.HexColor("#475569"), spaceAfter=1)
    callout = ParagraphStyle("IntelCallout", parent=body, fontName="Helvetica-Bold", fontSize=8.2, leading=10.5, textColor=colors.HexColor("#075985"), backColor=colors.HexColor("#e0f2fe"), borderColor=colors.HexColor("#7dd3fc"), borderWidth=0.7, borderPadding=7, spaceAfter=8)
    code_style = ParagraphStyle("IntelCode", parent=styles["Code"], fontName="Courier", fontSize=6.7, leading=8.2, textColor=colors.HexColor("#0f172a"), backColor=colors.HexColor("#f8fafc"), borderColor=colors.HexColor("#cbd5e1"), borderWidth=0.5, borderPadding=7, leftIndent=0, rightIndent=0, spaceBefore=3, spaceAfter=6)

    def p(value: Any, style: Any, limit: int = 1200) -> Any:
        return _paragraph(value, style, limit=limit)

    story: list[Any] = [
        p("Repository Quality and Repair Intelligence", title),
        p(
            "This appendix is evidence-bound and report-only. NICO has not changed, committed, pushed, deployed, or opened a pull request against the assessed repository. Suggested code remains unverified until the exact repository tests pass and a human approves implementation.",
            callout,
            limit=1400,
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
        for finding in quality_findings[:12]:
            severity = str(finding.get("severity") or "unknown").upper()
            heading = f"{severity} - {finding.get('title') or finding.get('code') or 'Quality finding'}"
            heading_style = ParagraphStyle(
                f"Quality{severity}{len(story)}",
                parent=h3,
                textColor=colors.HexColor(_severity_color(severity)),
            )
            block = [p(heading, heading_style)]
            if finding.get("business_impact"):
                block.append(p(f"Business impact: {finding.get('business_impact')}", body, limit=1000))
            if finding.get("technical_impact"):
                block.append(p(f"Technical impact: {finding.get('technical_impact')}", small, limit=1000))
            if finding.get("recommendation"):
                block.append(p(f"Recommended action: {finding.get('recommendation')}", body, limit=1200))
            block.extend(_bullets(list(finding.get("evidence") or []), small, max_items=5))
            story.extend(block)
            story.append(Spacer(1, 0.04 * inch))
    if quality.get("unavailable"):
        story.append(p("Unavailable or Permission-Limited Evidence", h3))
        story.extend(_bullets(list(quality.get("unavailable") or []), small, max_items=10))

    repairs = result.get("repair_intelligence") if isinstance(result.get("repair_intelligence"), dict) else {}
    candidates = [item for item in repairs.get("candidates", []) or [] if isinstance(item, dict)]
    story.append(PageBreak())
    story.append(p("Prioritized Repair Intelligence", h2))
    story.append(p(
        f"Final reconciled repair candidates: {repairs.get('candidate_count', len(candidates))}. Report-only code candidates: {repairs.get('code_suggestion_count', 0)}. Candidate ordering uses severity, confidence, exploitability, RYE priority, and TGRM repair level.",
        subtitle,
    ))

    if candidates:
        rows = [[p("Rank", label), p("Finding", label), p("Severity", label), p("Priority", label), p("TGRM", label), p("Code", label)]]
        for item in candidates[:_MAX_DETAILED_CANDIDATES]:
            tgrm = item.get("tgrm") if isinstance(item.get("tgrm"), dict) else {}
            suggestion = item.get("code_suggestion") if isinstance(item.get("code_suggestion"), dict) else {}
            rows.append([
                p(f"P{item.get('rank', '?')}", small),
                p(item.get("title") or "Repair candidate", small, limit=280),
                p(str(item.get("severity") or "unknown").upper(), small),
                p(str(item.get("priority_score") or "N/A"), small),
                p(f"L{tgrm.get('level', '?')}", small),
                p("Available" if suggestion.get("status") == "available" else "Context needed", small),
            ])
        table = Table(rows, colWidths=[0.38 * inch, 3.47 * inch, 0.67 * inch, 0.62 * inch, 0.48 * inch, 1.46 * inch], repeatRows=1)
        table_style: list[tuple[Any, ...]] = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#075985")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for index, item in enumerate(candidates[:_MAX_DETAILED_CANDIDATES], start=1):
            table_style.append(("TEXTCOLOR", (2, index), (2, index), colors.HexColor(_severity_color(item.get("severity")))))
        table.setStyle(TableStyle(table_style))
        story.append(table)
        story.append(Spacer(1, 0.10 * inch))

    for item in candidates[:_MAX_DETAILED_CANDIDATES]:
        rank = item.get("rank", "?")
        title_text = item.get("title") or "Repair candidate"
        severity = str(item.get("severity") or "unknown").upper()
        tgrm = item.get("tgrm") if isinstance(item.get("tgrm"), dict) else {}
        meta = Table([[
            p(f"Severity\n{severity}", label),
            p(f"Priority\n{item.get('priority_score', 'N/A')}", label),
            p(f"Confidence\n{item.get('confidence', 'unknown')}", label),
            p(f"Exploitability\n{item.get('exploitability', 'unknown')}", label),
            p(f"TGRM\nLevel {tgrm.get('level', '?')}", label),
        ]], colWidths=[1.05 * inch, 1.05 * inch, 1.25 * inch, 1.35 * inch, 1.35 * inch])
        meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor(_severity_color(severity))),
        ]))
        story.append(KeepTogether([p(f"P{rank} - {title_text}", h3), meta]))
        if item.get("impact"):
            story.append(p(f"Impact: {item.get('impact')}", body, limit=1200))
        if item.get("technical_impact"):
            story.append(p(f"Technical impact: {item.get('technical_impact')}", small, limit=1200))
        if item.get("recommended_action"):
            story.append(p(f"Recommended action: {item.get('recommended_action')}", body, limit=1500))
        if tgrm.get("scope"):
            story.append(p(f"TGRM scope: {tgrm.get('scope')}", small, limit=900))
        affected = list(item.get("affected_files") or [])
        if affected:
            story.append(p("Affected files or systems", label))
            story.extend(_bullets(affected, small, max_items=12, limit=420))
        evidence = list(item.get("evidence") or [])
        if evidence:
            story.append(p("Evidence", label))
            story.extend(_bullets(evidence, small, max_items=6, limit=600))

        suggestion = item.get("code_suggestion") if isinstance(item.get("code_suggestion"), dict) else {}
        if suggestion.get("status") == "available":
            story.append(p("Suggested replacement code - not applied and not yet verified", h3))
            story.append(p(
                suggestion.get("accuracy_statement") or "This is a review candidate. Validate it against the exact repository context and pass the stated tests before adoption.",
                callout,
                limit=1100,
            ))
            story.append(Preformatted(html.escape(_wrapped_code(suggestion.get("suggested_code"))), code_style, maxLineLength=100))
            conditions = list(suggestion.get("applicability_conditions") or [])
            if conditions:
                story.append(p("Applicability conditions", label))
                story.extend(_bullets(conditions, small, max_items=8, limit=650))
            verification = list(suggestion.get("verification_steps") or [])
            if verification:
                story.append(p("Verification required", label))
                story.extend(_bullets(verification, small, max_items=8, limit=650))
        else:
            story.append(p(
                "Suggested code: unavailable. " + str(suggestion.get("reason") or "Additional exact file context and tests are required before NICO can provide a conservative replacement candidate."),
                small,
                limit=1000,
            ))
        if item.get("rollback_plan"):
            story.append(p(f"Rollback: {item.get('rollback_plan')}", small, limit=1000))
        story.append(Spacer(1, 0.10 * inch))

    if len(candidates) > _MAX_DETAILED_CANDIDATES:
        story.append(p(
            f"{len(candidates) - _MAX_DETAILED_CANDIDATES} additional candidate(s) are retained in the full Markdown/HTML and JSON evidence exports.",
            subtitle,
        ))

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
            "/Subject": "Evidence-bound technical assessment with structured repository quality and repair intelligence",
        }
        writer.add_metadata(metadata)
        output = io.BytesIO()
        writer.write(output)
        result["report_intelligence_pdf"] = {
            "status": "complete",
            "style": PDF_STYLE_VERSION,
            "structured_appendix": True,
            "raw_markdown_rendered": False,
            "candidate_count": int((repairs or {}).get("candidate_count") or 0) if isinstance(repairs, dict) else 0,
            "code_suggestion_count": int((repairs or {}).get("code_suggestion_count") or 0) if isinstance(repairs, dict) else 0,
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
        "raw_markdown_rendered": False,
        "report_only": True,
        "automatic_application_allowed": False,
    }


__all__ = [
    "PDF_STYLE_VERSION",
    "build_professional_intelligence_pdf",
    "install_professional_report_intelligence_pdf",
]
