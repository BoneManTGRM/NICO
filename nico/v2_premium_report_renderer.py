from __future__ import annotations

import base64
import hashlib
import io
import re
from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    DELIVERY_STATUS,
    EN_BOUNDARY,
    ES_BOUNDARY,
    REPORT_FINALITY,
)
from nico.comprehensive_report_package import _markdown, _pdf, _semantic_html
from nico.comprehensive_report_spanish_artifacts_v51 import _spanish_html, _spanish_pdf
from nico.comprehensive_report_spanish_text_v51 import _spanish_markdown

VERSION = "nico.v2.premium-report-renderer.v6.1"
_TIMESTAMP = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return language.startswith("es")


def _canonical_generated_at(canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    generated_at = _text(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp")
    )
    if not _TIMESTAMP.fullmatch(generated_at):
        raise ValueError("premium report renderer requires one canonical generated_at timestamp")
    return generated_at


def _clean_lines(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        item = _text(raw)
        if not item or not re.search(r"[A-Za-z0-9]", item):
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _score_pair(assessment: Mapping[str, Any]) -> tuple[int | None, int | None]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}

    def numeric(*values: Any) -> int | None:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            return max(0, min(100, int(round(value))))
        return None

    technical = numeric(
        assessment.get("technical_score"),
        maturity.get("technical_score"),
        maturity.get("presented_score"),
        maturity.get("score"),
    )
    adjusted = numeric(
        assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"),
        technical,
    )
    return technical, adjusted


def _score_summary_markdown(assessment: Mapping[str, Any], *, spanish: bool) -> str:
    technical, adjusted = _score_pair(assessment)
    technical_text = f"{technical}/100" if technical is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
    adjusted_text = f"{adjusted}/100" if adjusted is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
    if spanish:
        return (
            "## Resumen canónico de puntuación\n\n"
            f"- Madurez técnica: {technical_text}\n"
            f"- Ajuste por evidencia: {adjusted_text}\n"
        )
    return (
        "## Canonical Score Summary\n\n"
        f"- Technical maturity: {technical_text}\n"
        f"- Evidence-Adjusted: {adjusted_text}\n"
    )


def _prepend_score_summary_pdf(
    pdf_bytes: bytes,
    *,
    identity: Mapping[str, Any],
    assessment: Mapping[str, Any],
    spanish: bool,
) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    technical, adjusted = _score_pair(assessment)
    technical_text = f"{technical}/100" if technical is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
    adjusted_text = f"{adjusted}/100" if adjusted is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "CanonicalScoreTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=29,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=18,
    )
    body = ParagraphStyle(
        "CanonicalScoreBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#334155"),
        spaceAfter=8,
    )
    warning = ParagraphStyle(
        "CanonicalScoreWarning",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.8,
        borderPadding=9,
        spaceAfter=16,
    )
    heading = "Resumen canónico de puntuación" if spanish else "Canonical Score Summary"
    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    rows = [
        ["Repositorio" if spanish else "Repository", _text(identity.get("repository"))],
        ["Commit exacto" if spanish else "Exact commit", _text(identity.get("commit_sha"))],
        ["ID de ejecución" if spanish else "Run ID", _text(identity.get("run_id"))],
        ["Generado" if spanish else "Generated", _text(identity.get("generated_at"))],
        ["Madurez técnica" if spanish else "Technical maturity", technical_text],
        ["Ajuste por evidencia" if spanish else "Evidence-Adjusted", adjusted_text],
    ]
    table = Table(rows, colWidths=[1.65 * inch, 5.15 * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story = [
        Spacer(1, .65 * inch),
        Paragraph("NICO COMPREHENSIVE", title),
        Paragraph(heading, title),
        Paragraph(boundary, warning),
        table,
        Spacer(1, .2 * inch),
        Paragraph(
            "These two scores are separate: technical maturity summarizes scored technical controls, while Evidence-Adjusted reflects the confidence and completeness of retained evidence."
            if not spanish
            else "Estas dos puntuaciones son distintas: la madurez técnica resume los controles técnicos puntuados y el ajuste por evidencia refleja la confianza y completitud de la evidencia conservada.",
            body,
        ),
    ]
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.6 * inch,
        rightMargin=.6 * inch,
        topMargin=.6 * inch,
        bottomMargin=.6 * inch,
        invariant=1,
    )
    document.build(story)
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _stage(stage_id: str, title: str, summary: str, *, evidence: list[str] | None = None,
           findings: list[str] | None = None, unavailable: list[str] | None = None,
           status: str = "complete") -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "title": title,
        "status": status,
        "summary": summary,
        "evidence": _clean_lines(evidence),
        "findings": _clean_lines(findings),
        "unavailable": _clean_lines(unavailable),
    }


def _finding_lines(findings: list[Mapping[str, Any]]) -> list[str]:
    output: list[str] = []
    for item in findings:
        identifier = _text(item.get("finding_id") or item.get("id"))
        title = _text(item.get("title") or item.get("decision_title"))
        priority = _text(item.get("priority") or item.get("severity") or "P2")
        location = _text(item.get("location"))
        impact = _text(item.get("business_impact") or item.get("impact"))
        recommendation = _text(item.get("recommendation"))
        output.append(
            f"{priority} · {title} · {identifier} · {location or 'location not retained'} · "
            f"Impact: {impact or 'requires review'} · Recommendation: {recommendation or 'requires review'}"
        )
    return output


def _scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    evidence = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('state') or item.get('status'))}; "
        f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
        f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; "
        f"retained finding count={len(item.get('findings') or [])}"
        for item in records
    ]
    limitations = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('failure_reason') or item.get('reason') or 'scanner execution evidence incomplete')}"
        for item in incomplete
    ]
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    candidate = assessment.get("review_candidate_summary") if isinstance(assessment.get("review_candidate_summary"), Mapping) else {}
    review_required = int(candidate.get("review_required_total") or 0)
    return [
        _stage(
            "dependency_security_static_analysis",
            "Dependency, Security, and Static Analysis",
            f"{len(completed)} scanner execution record(s) completed; {review_required} candidate(s) remain pending human triage. Execution completion does not equal candidate disposition.",
            evidence=evidence,
            unavailable=limitations,
            status="complete" if not incomplete else "review_required",
        )
    ]


def _canonical_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    existing = [
        deepcopy(dict(item))
        for item in canonical.get("stage_summaries") or []
        if isinstance(item, Mapping)
    ]
    by_id = {_text(item.get("stage_id")): item for item in existing if _text(item.get("stage_id"))}
    for item in _scanner_stages(canonical):
        by_id[item["stage_id"]] = item

    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    executive = findings[:7]
    briefing = deepcopy(dict(by_id.get("risk_reduction_and_executive_briefing") or {}))
    briefing.update(
        _stage(
            "risk_reduction_and_executive_briefing",
            "Executive Risk Register and Decision Briefing",
            "The automated executive briefing and bounded priority register are complete for review; finding acceptance, residual-risk ownership, remediation commitment, and delivery authorization remain pending human disposition.",
            evidence=briefing.get("evidence"),
            findings=_finding_lines(executive),
            unavailable=briefing.get("unavailable") or briefing.get("limitations"),
            status="review_required",
        )
    )
    by_id["risk_reduction_and_executive_briefing"] = briefing

    roadmap = [item for item in canonical.get("roadmap") or [] if isinstance(item, Mapping)]
    roadmap_evidence: list[str] = []
    for window in roadmap:
        label = _text(window.get("window") or window.get("title"))
        objective = _text(window.get("objective"))
        if label and objective:
            roadmap_evidence.append(f"{label}: {objective}")
        elif label:
            roadmap_evidence.append(label)
        elif objective:
            roadmap_evidence.append(objective)
        for work in window.get("work_packages") or []:
            if not isinstance(work, Mapping):
                continue
            work_id = _text(work.get("work_package_id") or work.get("id"))
            title = _text(work.get("title") or work.get("objective"))
            owner = _text(work.get("owner_role") or work.get("owner"))
            effort = _text(work.get("effort") or work.get("effort_range"))
            parts = [part for part in (work_id, title) if part]
            details = [value for value in (f"owner={owner}" if owner else "", f"effort={effort}" if effort else "") if value]
            line = " · ".join(parts)
            if details:
                line = f"{line}; {'; '.join(details)}" if line else "; ".join(details)
            if line:
                roadmap_evidence.append(f"{label} · {line}" if label else line)

    roadmap_stage = deepcopy(dict(by_id.get("six_month_roadmap") or {}))
    if roadmap_stage or roadmap:
        roadmap_stage.update(
            _stage(
                "six_month_roadmap",
                "Six-Month Roadmap",
                "A six-month roadmap framework was derived from canonical technical findings. Dates, owners, sequencing, staffing, cost, business priority, and delivery commitments remain pending authorized stakeholder validation.",
                evidence=[*(roadmap_stage.get("evidence") or []), *roadmap_evidence],
                findings=roadmap_stage.get("findings"),
                unavailable=roadmap_stage.get("unavailable") or roadmap_stage.get("limitations"),
                status="framework_only",
            )
        )
        by_id["six_month_roadmap"] = roadmap_stage

    staffing = deepcopy(dict(by_id.get("staffing_sequencing_and_cost") or {}))
    if staffing:
        staffing.update(
            _stage(
                "staffing_sequencing_and_cost",
                _text(staffing.get("title")) or "Staffing, Sequencing, and Cost",
                "Role sequencing is advisory. Named people, capacity, rates, contract structure, geographic mix, budget, and commercial commitments remain pending authorized stakeholder validation.",
                evidence=staffing.get("evidence"),
                findings=staffing.get("findings"),
                unavailable=staffing.get("unavailable") or staffing.get("limitations"),
                status="framework_only",
            )
        )
        by_id["staffing_sequencing_and_cost"] = staffing

    return list(by_id.values())


def rebuild_premium_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {})) if isinstance(result.get("json"), Mapping) else {}
    identity = deepcopy(dict(canonical.get("identity") or {})) if isinstance(canonical.get("identity"), Mapping) else {}
    generated_at = _canonical_generated_at(canonical)
    identity["generated_at"] = generated_at
    identity["generation_timestamp"] = generated_at
    canonical["identity"] = identity
    canonical["generated_at"] = generated_at
    canonical["generation_timestamp"] = generated_at

    assessment = deepcopy(dict(canonical.get("assessment") or {})) if isinstance(canonical.get("assessment"), Mapping) else {}
    stages = _canonical_stages(canonical)
    canonical["stage_summaries"] = deepcopy(stages)
    assessment["stage_summaries"] = deepcopy(stages)
    canonical["assessment"] = assessment
    spanish = _is_spanish(canonical)
    score_summary = _score_summary_markdown(assessment, spanish=spanish)

    if spanish:
        markdown = _spanish_markdown(canonical).replace(
            "La evaluación automatizada terminó como borrador.",
            "La evaluación automatizada terminó como borrador automatizado pendiente de aprobación humana.",
        ).replace("BORRADOR", "BORRADOR AUTOMATIZADO PENDIENTE DE APROBACIÓN")
        marker = "## Resumen ejecutivo"
        markdown = markdown.replace(marker, f"{score_summary}\n{marker}", 1) if marker in markdown else f"{score_summary}\n{markdown}"
        if "CLIENT DELIVERY NOT AUTHORIZED" not in markdown:
            markdown += "\n<!-- CLIENT DELIVERY NOT AUTHORIZED -->\n"
        rendered_html = _spanish_html(markdown, "Evaluación Técnica Integral NICO")
        pdf_bytes, original_page_count = _spanish_pdf(canonical)
        pdf_bytes = _prepend_score_summary_pdf(pdf_bytes, identity=identity, assessment=assessment, spanish=True)
        page_count = original_page_count + 1
        pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
        pdf_error = None
    else:
        markdown = _markdown(dict(identity), dict(assessment), stages, generated_at).replace(
            "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
            f"{EN_BOUNDARY} — CLIENT DELIVERY NOT AUTHORIZED",
        )
        marker = "## Executive Decision Brief"
        markdown = markdown.replace(marker, f"{score_summary}\n{marker}", 1) if marker in markdown else f"{score_summary}\n{markdown}"
        title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
        rendered_html = _semantic_html(markdown, title)
        pdf_base64, pdf_error, original_page_count = _pdf(dict(identity), dict(assessment), stages, generated_at)
        pdf_bytes = base64.b64decode(pdf_base64) if pdf_base64 else b""
        if pdf_bytes.startswith(b"%PDF"):
            pdf_bytes = _prepend_score_summary_pdf(pdf_bytes, identity=identity, assessment=assessment, spanish=False)
            pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
            page_count = original_page_count + 1
        else:
            page_count = original_page_count

    if pdf_error or not pdf_base64 or not pdf_bytes.startswith(b"%PDF"):
        raise ValueError(f"premium PDF renderer failed: {pdf_error or 'invalid or empty PDF'}")

    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update({
        "version": VERSION,
        "rebuilt_from_repaired_canonical_truth": True,
        "markdown_html_pdf_share_one_canonical_population": True,
        "premium_renderer_restored_after_canonical_repair": True,
        "duplicate_full_finding_cards_not_rendered": True,
        "canonical_score_pair_explicit_in_all_formats": True,
        "canonical_generated_at_used_by_every_renderer": True,
        "legacy_aliases_hidden_from_client_artifacts": True,
        "bilingual_renderer_selected_from_canonical_language": True,
        "automated_draft_semantics_embedded": True,
        "page_count": page_count,
    })

    result.update({
        "json": canonical,
        "generated_at": generated_at,
        "generation_timestamp": generated_at,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": pdf_base64,
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
        "report_finality": REPORT_FINALITY,
        "approval_status": APPROVAL_STATUS,
        "delivery_status": DELIVERY_STATUS,
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "phase17_artifact_rebuild": phase17,
        "premium_report_renderer": {
            "version": VERSION,
            "premium_multi_chapter_layout": True,
            "executive_decision_brief": True,
            "weighted_scorecard": True,
            "canonical_score_summary": True,
            "evidence_health_summary": True,
            "executive_risk_register": True,
            "bounded_executive_finding_detail": True,
            "duplicate_full_finding_cards": False,
            "architecture_and_delivery_chapters": True,
            "roadmap_and_resourcing_chapters": True,
            "full_evidence_retained_in_structured_exports": True,
            "canonical_findings_only": True,
            "canonical_scanner_truth_only": True,
            "canonical_generated_at_only": True,
            "bilingual_premium_output": True,
            "page_count": page_count,
        },
    })
    return result


__all__ = ["VERSION", "rebuild_premium_client_artifacts"]
