from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from typing import Any, Mapping

from nico import v2_assessment_pipeline as _pipeline
from nico.dependency_materiality import classify_dependency_finding
from nico.v2_premium_evidence_appendix import rebuild_premium_client_artifacts_with_appendix

VERSION = "nico.v2.authoritative-premium-report.v1"
_ORIGINAL_BUILD = _pipeline.build_canonical_assessment
_ORIGINAL_HASH = _pipeline.canonical_truth_sha256
_PATCHED = False


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _scanner_name(value: Any) -> str:
    return _text(value).casefold().replace("_", "-")


def _non_production_path(value: Any) -> bool:
    path = _text(value).casefold().replace("\\", "/")
    path = re.sub(r":\d+(?::\d+)?$", "", path)
    segments = [item for item in path.split("/") if item]
    filename = segments[-1] if segments else ""
    return bool(
        filename.startswith("test_")
        or filename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or any(segment in {"test", "tests", "fixtures", "fixture", "generated", "vendor", "vendors", "dist", "build", "coverage"} for segment in segments)
    )


def _scanner_records(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = canonical.get("scanner_execution_records")
    if not isinstance(records, list):
        assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
        records = assessment.get("scanner_execution_records")
    return [deepcopy(dict(item)) for item in (records or []) if isinstance(item, Mapping)]


def _score_pair(assessment: Mapping[str, Any]) -> tuple[int | None, int | None]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    technical = next((score for raw in (
        truth.get("technical_score"), assessment.get("technical_score"), maturity.get("technical_score"),
        maturity.get("presented_score"), maturity.get("score"),
    ) if (score := _numeric(raw)) is not None), None)
    adjusted = next((score for raw in (
        truth.get("canonical_evidence_adjusted_score"), assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"), maturity.get("canonical_evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"), technical,
    ) if (score := _numeric(raw)) is not None), None)
    return technical, adjusted


def _synchronize_scores(canonical: dict[str, Any]) -> None:
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    maturity = deepcopy(dict(assessment.get("maturity_signal") or {}))
    technical, adjusted = _score_pair(assessment)
    if technical is not None:
        assessment["technical_score"] = technical
        for key in ("technical_score", "presented_score", "score", "source_score"):
            maturity[key] = technical
    if adjusted is not None:
        assessment["canonical_evidence_adjusted_score"] = adjusted
        assessment["evidence_adjusted_score"] = adjusted
        maturity["canonical_evidence_adjusted_score"] = adjusted
        maturity["evidence_adjusted_score"] = adjusted
    assessment["maturity_signal"] = maturity
    assessment["comprehensive_score_truth"] = {
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "aliases_synchronized": technical is not None and adjusted is not None,
        "authoritative_source": "canonical_assessment",
    }
    canonical["assessment"] = assessment


def _conflicts_with_scanner_truth(value: str, completed: set[str]) -> bool:
    lowered = value.casefold()
    negative = any(word in lowered for word in (" missing", " failed", " unavailable", " did not run", " not executed"))
    return negative and any(name and name in lowered for name in completed)


def _sanitize_container(value: Any, completed: set[str]) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_container(item, completed) for key, item in value.items()}
    if isinstance(value, list):
        output = []
        for item in value:
            cleaned = _sanitize_container(item, completed)
            if isinstance(cleaned, str) and not cleaned:
                continue
            output.append(cleaned)
        return output
    if isinstance(value, tuple):
        return tuple(_sanitize_container(list(value), completed))
    if isinstance(value, str):
        return "" if _conflicts_with_scanner_truth(value, completed) else value
    return deepcopy(value)


def _dependency_dispositions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dispositions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        tool = _scanner_name(record.get("scanner_name") or record.get("tool"))
        category = _text(record.get("category")).casefold()
        if category != "dependency" and tool not in {"osv", "osv-scanner", "pip-audit", "npm-audit"}:
            continue
        for raw in record.get("findings") or []:
            if not isinstance(raw, Mapping):
                continue
            item = classify_dependency_finding(raw)
            fingerprint = _text(item.get("dependency_fingerprint"))
            if fingerprint and fingerprint in seen:
                continue
            if fingerprint:
                seen.add(fingerprint)
            dispositions.append(item)
    return dispositions


def _classify_findings(canonical: dict[str, Any]) -> None:
    source = canonical.get("canonical_findings") if isinstance(canonical.get("canonical_findings"), list) else []
    repaired: list[dict[str, Any]] = []
    for raw in source:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        location = item.get("location") or item.get("path")
        if _non_production_path(location):
            item.update({
                "production_scope": False,
                "production_relevant": False,
                "scope": "non_production",
                "observation_class": "non_production_observation",
                "technical_score_impact": "none",
                "requires_human_triage": False,
            })
        category = _text(item.get("category")).casefold()
        if "depend" in category or _text(item.get("finding_family")).casefold().startswith("osv"):
            item.update(classify_dependency_finding(item))
            item["requires_human_triage"] = item.get("disposition") == "triage_required"
        repaired.append(item)
    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        canonical[surface] = deepcopy(repaired)
    scored = [item for item in repaired if item.get("technical_score_impact") != "none"]
    canonical["executive_risk_register"] = deepcopy(scored[:7])
    canonical["priority_findings"] = deepcopy(scored[:5])


def project_authoritative_canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    canonical = deepcopy(dict(value))
    _synchronize_scores(canonical)
    records = _scanner_records(canonical)
    completed = {_scanner_name(item.get("scanner_name") or item.get("tool")) for item in records if item.get("completed") is True}
    canonical["assessment"] = _sanitize_container(canonical.get("assessment") or {}, completed)
    canonical["stage_summaries"] = _sanitize_container(canonical.get("stage_summaries") or [], completed)
    canonical["scanner_execution_records"] = records
    canonical["assessment"]["scanner_execution_records"] = deepcopy(records)
    _classify_findings(canonical)
    dispositions = _dependency_dispositions(records)
    canonical["dependency_dispositions"] = dispositions
    canonical["assessment"]["dependency_disposition_summary"] = {
        "total_advisories": len(dispositions),
        "verified_material": sum(item["disposition"] == "verified_material" for item in dispositions),
        "triage_required": sum(item["disposition"] == "triage_required" for item in dispositions),
        "untriaged_records_reduce_assurance_only": True,
    }
    canonical.update({
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "assessment_state": "review_required",
        "human_review_required": True,
        "client_delivery_allowed": False,
    })
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update({
        "authoritative_premium_truth_projection": True,
        "stale_scanner_section_data_removed": True,
        "dependency_materiality_requires_disposition": True,
        "test_and_generated_code_excluded_from_production_scoring": True,
        "single_score_pair_for_all_renderers": True,
    })
    canonical["v2_pipeline_contract"] = contract
    return canonical


def _authoritative_build(report: Mapping[str, Any]) -> dict[str, Any]:
    return project_authoritative_canonical(_ORIGINAL_BUILD(report))


def _authoritative_hash(canonical: Mapping[str, Any]) -> str:
    return _ORIGINAL_HASH(project_authoritative_canonical(canonical))


def install_pipeline_projection() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _pipeline.build_canonical_assessment = _authoritative_build
    _pipeline.canonical_truth_sha256 = _authoritative_hash
    _PATCHED = True


def _clean_markdown(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> str:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    technical, adjusted = _score_pair(assessment)
    text = re.sub(
        r"\n## (?:Canonical Score Summary|Resumen canónico de puntuación)\n.*?(?=\n## )",
        "\n",
        markdown,
        flags=re.S,
    )
    replacements = {
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED": "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED — CLIENT DELIVERY NOT AUTHORIZED",
        "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED": "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED · CLIENT DELIVERY NOT AUTHORIZED",
        "The package is a review-gated draft": "The package is a final automated assessment pending human approval",
        "The report is an evidence-bound draft.": "The report is a final automated assessment pending human approval.",
        "The automated assessment is complete only as a draft.": "The automated assessment is complete and pending human approval.",
        "DRAFT": "FINAL REPORT PENDING HUMAN APPROVAL",
        "BORRADOR": "INFORME FINAL PENDIENTE DE APROBACIÓN",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if technical is not None:
        text = re.sub(r"(?i)(Presented score:\s*)\d+/100", rf"\g<1>{technical}/100", text)
        text = re.sub(r"(?i)(Technical maturity:\s*)\d+/100", rf"\g<1>{technical}/100", text)
        text = re.sub(r"(?i)(Madurez técnica:\s*)\d+/100", rf"\g<1>{technical}/100", text)
    if adjusted is not None:
        text = re.sub(r"(?i)(Evidence-Adjusted:\s*)\d+/100", rf"\g<1>{adjusted}/100", text)
        text = re.sub(r"(?i)(Ajuste por evidencia:\s*)\d+/100", rf"\g<1>{adjusted}/100", text)
    completed = {_scanner_name(item.get("scanner_name") or item.get("tool")) for item in _scanner_records(canonical) if item.get("completed") is True}
    text = "\n".join(line for line in text.splitlines() if not _conflicts_with_scanner_truth(line, completed)).strip() + "\n"
    banner = (
        "**INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA**"
        if spanish
        else "**FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED · CLIENT DELIVERY NOT AUTHORIZED**"
    )
    if banner not in text:
        rows = text.splitlines()
        rows.insert(2 if len(rows) >= 2 else len(rows), banner)
        text = "\n".join(rows).strip() + "\n"
    if "CLIENT DELIVERY NOT AUTHORIZED" not in text:
        text += "\n<!-- CLIENT DELIVERY NOT AUTHORIZED -->\n"
    return text


def _html_from_markdown(markdown: str, title: str, *, spanish: bool) -> str:
    blocks: list[str] = []
    list_items: list[str] = []

    def flush() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("<!--"):
            blocks.append(line)
        elif line.startswith("### "):
            flush(); blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            flush(); blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            flush(); blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("- [ ] "):
            list_items.append(f"<li class='check'>☐ {html.escape(line[6:])}</li>")
        elif line.startswith("- ") or line.startswith("  - "):
            list_items.append(f"<li>{html.escape(line.lstrip()[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            flush(); blocks.append(f"<p class='warning'>{html.escape(line.strip('*'))}</p>")
        else:
            flush(); blocks.append(f"<p>{html.escape(line)}</p>")
    flush()
    language = "es" if spanish else "en"
    badge = "INFORME FINAL · APROBACIÓN PENDIENTE" if spanish else "FINAL REPORT · APPROVAL PENDING"
    return f"""<!doctype html><html lang='{language}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#050b18;color:#dce8fa;font:15px/1.6 Inter,system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:34px 20px 80px}}header{{position:relative;overflow:hidden;padding:42px;border:1px solid #18304f;border-radius:26px;background:linear-gradient(145deg,#071224,#0b1f39)}}header:after{{content:'';position:absolute;width:440px;height:440px;border-radius:50%;right:-180px;top:-260px;background:#0c4a6e55}}header h1{{position:relative;margin:0;color:white;font-size:clamp(30px,5vw,50px);line-height:1.06}}.badge{{position:relative;display:inline-block;margin-top:18px;padding:8px 13px;border:1px solid #f59e0b;border-radius:999px;background:#3b2108;color:#fde68a;font-weight:800}}article{{margin-top:24px;padding:30px;border:1px solid #18304f;border-radius:24px;background:#081426}}h1{{color:white}}h2{{margin-top:40px;padding-top:25px;border-top:1px solid #18304f;color:#55d7f4}}h3{{margin-top:26px;color:#dff8ff}}p,li{{color:#bdcbe0}}ul{{padding-left:24px}}li{{margin:7px 0}}.check{{list-style:none;margin-left:-20px}}.warning{{padding:15px;border:1px solid #f59e0b;border-radius:14px;background:#3b2108;color:#fde68a;font-weight:800}}</style></head><body><main><header><h1>{html.escape(title)}</h1><span class='badge'>{badge}</span></header><article>{''.join(blocks)}</article></main></body></html>"""


def _pdf_from_markdown(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> tuple[bytes, int]:
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    technical, adjusted = _score_pair(assessment)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    cover_title = ParagraphStyle("CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=colors.HexColor("#0f172a"), alignment=TA_CENTER, spaceAfter=15)
    cover_body = ParagraphStyle("CoverBody", parent=styles["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#334155"), alignment=TA_CENTER)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#075985"), spaceBefore=8, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=12.5, textColor=colors.HexColor("#334155"), spaceAfter=5)
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=13, firstLineIndent=-8)
    warning = ParagraphStyle("Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=8, spaceBefore=8, spaceAfter=8)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value, 9000)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#061326"))
        canvas.rect(0, 0, letter[0], .48 * inch, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#cbd5e1"))
        canvas.drawString(.55 * inch, .18 * inch, f"NICO Comprehensive · {_text(identity.get('run_id'), 54)} · FINAL PENDING APPROVAL")
        canvas.drawRightString(7.95 * inch, .18 * inch, f"Page {doc.page}")
        canvas.restoreState()

    story: list[Any] = [
        Spacer(1, .72 * inch),
        p("NICO", ParagraphStyle("Brand", parent=cover_title, fontSize=17, textColor=colors.HexColor("#0284c7"))),
        p("Evaluación Técnica Integral" if spanish else "Comprehensive Technical Assessment", cover_title),
        p(_text(identity.get("repository")), cover_body),
        Spacer(1, .34 * inch),
    ]
    score_rows = [
        ["Madurez técnica" if spanish else "Technical maturity", f"{technical}/100" if technical is not None else "NOT SCORED"],
        ["Ajuste por evidencia" if spanish else "Evidence-Adjusted", f"{adjusted}/100" if adjusted is not None else "NOT SCORED"],
    ]
    score_table = Table(score_rows, colWidths=[2.35 * inch, 1.35 * inch])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0b213b")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), .6, colors.HexColor("#1e7494")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story += [score_table, Spacer(1, .35 * inch), p(f"Run ID: {_text(identity.get('run_id'))}", cover_body), p(f"Exact commit: {_text(identity.get('commit_sha'))}", cover_body), Spacer(1, .25 * inch), p("INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA BLOQUEADA" if spanish else "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED", warning), PageBreak()]
    first_heading = True
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith("# NICO"):
            continue
        if line.startswith("## "):
            if not first_heading:
                story.append(PageBreak())
            first_heading = False
            story.append(p(line[3:], h1))
        elif line.startswith("### "):
            story.append(p(line[4:], h2))
        elif line.startswith("- [ ] "):
            story.append(p("☐ " + line[6:], bullet))
        elif line.startswith("- ") or line.startswith("  - "):
            story.append(p("• " + line.lstrip()[2:], bullet))
        elif line.startswith("**") and line.endswith("**"):
            story.append(p(line.strip("*"), warning))
        else:
            story.append(p(line, body))
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=.55 * inch, rightMargin=.55 * inch, topMargin=.58 * inch, bottomMargin=.68 * inch, invariant=1, title="NICO Comprehensive Technical Assessment", author="NICO")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf = buffer.getvalue()
    return pdf, len(PdfReader(io.BytesIO(pdf)).pages)


def rebuild_authoritative_premium_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(dict(package))
    canonical = project_authoritative_canonical(prepared.get("json") if isinstance(prepared.get("json"), Mapping) else {})
    prepared["json"] = canonical
    result = deepcopy(rebuild_premium_client_artifacts_with_appendix(prepared))
    canonical = project_authoritative_canonical(result.get("json") if isinstance(result.get("json"), Mapping) else canonical)
    spanish = _text(canonical.get("report_language") or canonical.get("locale")).casefold().startswith("es")
    markdown = _clean_markdown(str(result.get("markdown") or ""), canonical, spanish=spanish)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = "Evaluación Técnica Integral NICO" if spanish else f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    rendered_html = _html_from_markdown(markdown, title, spanish=spanish)
    pdf, page_count = _pdf_from_markdown(markdown, canonical, spanish=spanish)
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({
        "version": VERSION,
        "old_premium_layout_restored": True,
        "new_canonical_system_is_sole_truth": True,
        "plain_canonical_score_page_removed": True,
        "dark_branded_cover_restored": True,
        "stale_scanner_copy_absent": True,
        "finality_consistent": True,
        "dependency_disposition_required": True,
        "test_only_score_impact_removed": True,
        "page_count": page_count,
    })
    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update({"version": VERSION, "authoritative_truth_projected_before_render": True, "page_count": page_count})
    result.update({
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_error": None,
        "pdf_available": True,
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
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
        "premium_report_renderer": contract,
    })
    return result


__all__ = [
    "VERSION",
    "install_pipeline_projection",
    "project_authoritative_canonical",
    "rebuild_authoritative_premium_artifacts",
]
