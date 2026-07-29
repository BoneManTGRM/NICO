from __future__ import annotations

import base64
import hashlib
import html
import io
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Iterable, Mapping

from nico import v2_premium_report_renderer_legacy as _legacy

VERSION = "nico.v2.premium-report-renderer.v6"


def __getattr__(name: str) -> Any:
    return getattr(_legacy, name)


_FINAL_EN = "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED · CLIENT DELIVERY NOT AUTHORIZED"
_FINAL_ES = "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA"


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return language.startswith("es")


def _score_pair(assessment: Mapping[str, Any]) -> tuple[int | None, int | None]:
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}

    def numeric(*values: Any) -> int | None:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            return max(0, min(100, int(round(value))))
        return None

    technical = numeric(
        truth.get("technical_score"), assessment.get("technical_score"),
        maturity.get("technical_score"), maturity.get("presented_score"), maturity.get("score"),
    )
    adjusted = numeric(
        truth.get("canonical_evidence_adjusted_score"),
        assessment.get("canonical_evidence_adjusted_score"), assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"), maturity.get("evidence_adjusted_score"), technical,
    )
    return technical, adjusted


def _dependency_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    rows = [item for item in canonical.get("dependency_disposition") or [] if isinstance(item, Mapping)]
    heading = "## Clasificación de dependencias" if spanish else "## Dependency Disposition"
    lines = [heading, ""]
    if not rows:
        lines.append(
            "- No se conservaron avisos OSV en la población canónica."
            if spanish else "- No OSV advisory records were retained in the canonical scanner population."
        )
        return "\n".join(lines)
    if spanish:
        lines += [
            "Los avisos no clasificados reducen la confianza, no la madurez técnica, hasta verificar materialidad.", "",
            "| Aviso | Paquete | Instalada | Corregida | Alcance | Accesibilidad | Disposición | Impacto |",
            "|---|---|---|---|---|---|---|---|",
        ]
    else:
        lines += [
            "Untriaged advisories reduce assurance, not technical maturity, until materiality is verified.", "",
            "| Advisory | Package | Installed | Fixed | Scope | Reachability | Disposition | Score impact |",
            "|---|---|---|---|---|---|---|---|",
        ]
    for item in rows:
        impact = "Sí" if spanish and item.get("technical_score_impact") else "No, solo confianza" if spanish else "Yes" if item.get("technical_score_impact") else "No, assurance only"
        lines.append(
            f"| {_text(item.get('advisory_id'))} | {_text(item.get('package'))} | "
            f"{_text(item.get('installed_version'))} | {_text(item.get('fixed_version'))} | "
            f"{_text(item.get('scope'))} | {_text(item.get('reachability'))} | "
            f"{_text(item.get('disposition'))} | {impact} |"
        )
    return "\n".join(lines)


def _build_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    stages = _legacy._canonical_stages(canonical)
    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    generated = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if spanish:
        markdown = _legacy._spanish_markdown(canonical)
        markdown = markdown.replace("BORRADOR", "INFORME FINAL PENDIENTE DE APROBACIÓN")
        markdown = markdown.replace(
            "La evaluación automatizada terminó como borrador.",
            "La evaluación automatizada terminó como informe final pendiente de aprobación humana.",
        )
        boundary = f"**{_FINAL_ES}**"
        if boundary not in markdown:
            markdown = boundary + "\n\n" + markdown
        dependency = _dependency_markdown(canonical, spanish=True)
        marker = "## Puerta de revisión y entrega"
        markdown = markdown.replace(marker, f"{dependency}\n\n{marker}", 1) if marker in markdown else markdown.rstrip() + "\n\n" + dependency
        if "CLIENT DELIVERY NOT AUTHORIZED" not in markdown:
            markdown += "\n<!-- CLIENT DELIVERY NOT AUTHORIZED -->\n"
        return markdown

    markdown = _legacy._markdown(dict(identity), dict(assessment), stages, generated)
    markdown = markdown.replace(
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
        _FINAL_EN,
    ).replace(
        "The package is a review-gated draft:",
        "The package is a final automated report pending human approval:",
    ).replace(
        "The report is an evidence-bound draft.",
        "The report is an evidence-bound final automated report pending human approval.",
    ).replace(
        "The automated assessment is complete only as a draft.",
        "The automated assessment package is complete and pending human approval.",
    )
    detailed = _legacy._detailed_findings_markdown(findings, spanish=False)
    dependency = _dependency_markdown(canonical, spanish=False)
    marker = "## Delivery Status"
    insertion = f"{dependency}\n\n{detailed}\n\n"
    markdown = markdown.replace(marker, insertion + marker, 1) if marker in markdown else markdown.rstrip() + "\n\n" + insertion
    return markdown


def _html(markdown: str, title: str, *, spanish: bool) -> str:
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
        rows: list[str] = []
        for index, line in enumerate(table_lines):
            cells = [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            if index == 1 and all(set(cell) <= {"-", ":"} for cell in cells):
                continue
            tag = "th" if index == 0 else "td"
            rows.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
        blocks.append('<div class="table-wrap"><table>' + "".join(rows) + "</table></div>")
        table_lines = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            flush_list(); table_lines.append(line); continue
        flush_table()
        if not line:
            flush_list()
        elif line.startswith("<!--"):
            blocks.append(line)
        elif line.startswith("### "):
            flush_list(); blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_list(); blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_list(); blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("- [ ] "):
            list_items.append(f"<li>☐ {html.escape(line[6:])}</li>")
        elif line.startswith("  - "):
            list_items.append(f"<li>{html.escape(line[4:])}</li>")
        elif line.startswith("- "):
            list_items.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            flush_list(); blocks.append(f'<p class="warning">{html.escape(line.strip("*"))}</p>')
        else:
            flush_list(); blocks.append(f"<p>{html.escape(line)}</p>")
    flush_list(); flush_table()
    lang = "es" if spanish else "en"
    boundary = _FINAL_ES if spanish else _FINAL_EN
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>
:root{{color-scheme:dark}}body{{margin:0;background:#050b18;color:#dbeafe;font:15px/1.58 Inter,system-ui,sans-serif}}main{{max-width:1160px;margin:auto;padding:34px 20px 76px}}header{{background:linear-gradient(135deg,#071124,#0d2743);border:1px solid #1e4d70;border-radius:26px;padding:36px;margin-bottom:22px;box-shadow:0 22px 70px #0008}}header h1{{margin:0;color:#fff;font-size:clamp(30px,5vw,52px);line-height:1.04}}.eyebrow{{color:#38bdf8;font-weight:900;letter-spacing:.14em;text-transform:uppercase}}.badge{{display:inline-block;margin-top:16px;padding:8px 13px;border:1px solid #f59e0b;border-radius:999px;color:#fde68a;background:#4a2406;font-weight:800}}article{{background:#0b172c;border:1px solid #274060;border-radius:24px;padding:30px}}h1{{color:#fff}}h2{{color:#7dd3fc;border-top:1px solid #274060;padding-top:25px;margin-top:36px}}h3{{color:#e0f2fe}}p,li{{color:#cbd5e1}}.warning{{padding:15px;border:1px solid #f59e0b;border-radius:14px;background:#4a2406;color:#fde68a;font-weight:800}}.table-wrap{{overflow:auto;margin:16px 0;border:1px solid #274060;border-radius:14px}}table{{width:100%;border-collapse:collapse;background:#0d1a31}}th,td{{border-bottom:1px solid #274060;padding:10px;text-align:left;vertical-align:top}}th{{color:#fff;background:#0c4a6e}}
</style></head><body><main><header><div class="eyebrow">NICO Comprehensive</div><h1>{html.escape(title)}</h1><span class="badge">{html.escape(boundary)}</span></header><article>{''.join(blocks)}</article></main></body></html>"""


def _pdf(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    scanners = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    technical, adjusted = _score_pair(assessment)
    navy = colors.HexColor("#071124")
    navy2 = colors.HexColor("#0d2743")
    cyan = colors.HexColor("#38bdf8")
    pale = colors.HexColor("#dbeafe")
    amber = colors.HexColor("#f59e0b")
    styles = getSampleStyleSheet()
    cover_title = ParagraphStyle("CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=29, leading=34, textColor=colors.white, alignment=TA_LEFT, spaceAfter=16)
    cover_label = ParagraphStyle("CoverLabel", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=cyan, spaceAfter=8)
    cover_body = ParagraphStyle("CoverBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=14, textColor=pale, spaceAfter=7)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=navy, spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#075985"), spaceBefore=8, spaceAfter=6)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=navy, spaceBefore=6, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.6, leading=12.2, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("Small", parent=body, fontSize=7.2, leading=9.4, textColor=colors.HexColor("#475569"))
    warning = ParagraphStyle("Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=amber, borderWidth=.8, borderPadding=9, spaceAfter=10)
    card_title = ParagraphStyle("CardTitle", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.2, leading=10, textColor=cyan, alignment=TA_CENTER)
    card_value = ParagraphStyle("CardValue", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=21, leading=23, textColor=colors.white, alignment=TA_CENTER)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 6000)), style)

    def cover(canvas: Any, doc: Any) -> None:
        canvas.saveState(); canvas.setFillColor(navy); canvas.rect(0, 0, letter[0], letter[1], stroke=0, fill=1)
        canvas.setFillColor(navy2); canvas.circle(7.4 * inch, 9.6 * inch, 2.7 * inch, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#0b5f84")); canvas.circle(.8 * inch, .8 * inch, 1.5 * inch, stroke=0, fill=1)
        canvas.restoreState()

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState(); canvas.setFont("Helvetica", 7); canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .36 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 48)} · FINAL · APPROVAL PENDING")
        canvas.drawRightString(7.95 * inch, .36 * inch, f"Page {doc.page}"); canvas.restoreState()

    boundary = _FINAL_ES if spanish else _FINAL_EN
    title = "Evaluación Técnica Integral" if spanish else "Comprehensive Technical Assessment"
    story: list[Any] = [
        Spacer(1, .78 * inch), p("NICO COMPREHENSIVE", cover_label), p(title, cover_title),
        p(identity.get("repository"), ParagraphStyle("Repo", parent=cover_body, fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.white)),
        Spacer(1, .32 * inch), p(boundary, ParagraphStyle("CoverWarning", parent=cover_body, fontName="Helvetica-Bold", textColor=colors.HexColor("#fde68a"), backColor=colors.HexColor("#4a2406"), borderColor=amber, borderWidth=.8, borderPadding=10)),
        Spacer(1, .32 * inch), p(("ID de ejecución" if spanish else "Run ID") + f": {_text(identity.get('run_id'))}", cover_body),
        p(("Commit exacto" if spanish else "Exact commit") + f": {_text(identity.get('commit_sha'))}", cover_body),
        PageBreak(), p("Panel ejecutivo" if spanish else "Executive Dashboard", h1),
    ]
    cards = Table([
        [p("MADUREZ TÉCNICA" if spanish else "TECHNICAL MATURITY", card_title), p("AJUSTE POR EVIDENCIA" if spanish else "EVIDENCE-ADJUSTED", card_title), p("ANALIZADORES COMPLETOS" if spanish else "SCANNERS COMPLETE", card_title)],
        [p(f"{technical}/100" if technical is not None else "N/A", card_value), p(f"{adjusted}/100" if adjusted is not None else "N/A", card_value), p(f"{sum(item.get('completed') is True for item in scanners)}/{len(scanners)}", card_value)],
    ], colWidths=[2.35 * inch] * 3)
    cards.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), navy2), ("BOX", (0, 0), (-1, -1), .8, cyan), ("INNERGRID", (0, 0), (-1, -1), .35, colors.HexColor("#1e4d70")), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story += [cards, Spacer(1, .2 * inch), p(assessment.get("executive_summary") or "Automated assessment complete; human approval remains required.", body), PageBreak()]

    major = {
        "Executive Decision Brief", "Technical Scorecard", "Evidence Foundation", "Deep Technical Diligence",
        "Business and Delivery Context", "Roadmap, Resourcing, and Decision", "Dependency Disposition",
        "Detailed Canonical Findings", "Human Review Checklist", "Delivery Status",
        "Resumen ejecutivo", "Clasificación de dependencias", "Hallazgos canónicos detallados",
        "Apéndice de evidencia", "Puerta de revisión y entrega",
    }
    table_lines: list[str] = []

    def flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        parsed = [[cell.strip() for cell in line.strip("|").split("|")] for line in table_lines]
        if len(parsed) > 1 and all(set(cell) <= {"-", ":"} for cell in parsed[1]):
            parsed.pop(1)
        width = 7.2 * inch / max(1, len(parsed[0]))
        rows = [[p(cell, small) for cell in row] for row in parsed]
        table = Table(rows, colWidths=[width] * len(parsed[0]), repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])]))
        story.append(table); story.append(Spacer(1, .12 * inch)); table_lines = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            table_lines.append(line); continue
        flush_table()
        if not line or line.startswith("<!--") or line.startswith("# "):
            continue
        if line.startswith("## "):
            heading = line[3:]
            if heading in major and story and not isinstance(story[-1], PageBreak):
                story.append(PageBreak())
            story.append(p(heading, h1)); continue
        if line.startswith("### "):
            story.append(p(line[4:], h2)); continue
        if line.startswith("- [ ] "):
            story.append(p("☐ " + line[6:], small)); continue
        if line.startswith("  - "):
            story.append(p("• " + line[4:], small)); continue
        if line.startswith("- "):
            story.append(p("• " + line[2:], small)); continue
        if line.startswith("**") and line.endswith("**"):
            story.append(p(line.strip("*"), warning)); continue
        story.append(p(line, body))
    flush_table()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.58 * inch, bottomMargin=.62 * inch, invariant=1, title=title, author="NICO")
    doc.build(story, onFirstPage=cover, onLaterPages=footer)
    return buffer.getvalue()


def rebuild_premium_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {})) if isinstance(result.get("json"), Mapping) else {}
    spanish = _is_spanish(canonical)
    markdown = _build_markdown(canonical, spanish=spanish)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = ("Evaluación Técnica Integral NICO" if spanish else "NICO Comprehensive Technical Assessment") + f" — {_text(identity.get('repository'))}"
    rendered_html = _html(markdown, title, spanish=spanish)
    pdf_bytes = _pdf(markdown, canonical, spanish=spanish)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("premium PDF renderer failed: invalid or empty PDF")
    from pypdf import PdfReader
    page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)

    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update({
        "version": VERSION,
        "rebuilt_from_repaired_canonical_truth": True,
        "markdown_html_pdf_share_one_canonical_population": True,
        "old_visual_shell_new_canonical_engine": True,
        "dark_branded_cover_restored": True,
        "executive_dashboard_restored": True,
        "plain_canonical_score_summary_removed": True,
        "canonical_scanner_truth_only": True,
        "dependency_disposition_rendered": True,
        "non_production_findings_excluded_from_score_impact": True,
        "finality_semantics_embedded": True,
        "page_count": page_count,
    })
    result.update({
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "pdf_error": None,
        "pdf_available": True,
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "status": "review_required",
        "assessment_state": "review_required",
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "phase17_artifact_rebuild": phase17,
        "premium_report_renderer": {
            "version": VERSION,
            "premium_multi_chapter_layout": True,
            "old_system_visual_shell": True,
            "new_canonical_system_engine": True,
            "dark_branded_cover": True,
            "executive_dashboard": True,
            "weighted_scorecard": True,
            "canonical_score_summary": False,
            "evidence_health_summary": True,
            "dependency_disposition": True,
            "executive_risk_register": True,
            "detailed_canonical_finding_cards": True,
            "architecture_and_delivery_chapters": True,
            "roadmap_and_resourcing_chapters": True,
            "full_evidence_appendix": True,
            "canonical_findings_only": True,
            "canonical_scanner_truth_only": True,
            "bilingual_premium_output": True,
            "page_count": page_count,
        },
    })
    return result


__all__ = ["VERSION", "rebuild_premium_client_artifacts"]
