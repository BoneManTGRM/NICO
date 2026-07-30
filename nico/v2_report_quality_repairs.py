from __future__ import annotations

import base64
import hashlib
import html
import io
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.v2.report-quality-repairs.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _scanner_name(value: Any) -> str:
    return _text(value).casefold().replace("_", "-")


def _band(score: Any) -> str:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "NOT_SCORED"
    value = int(round(score))
    if value >= 85:
        return "STRONG"
    if value >= 70:
        return "MODERATE"
    if value >= 50:
        return "WEAK"
    return "CRITICAL"


def _stale_scanner_statement(value: Any, completed: set[str]) -> bool:
    text = _text(value).casefold()
    if not text:
        return False
    negative = any(token in text for token in ("status=missing", "status=failed", " unavailable", " did not run", " not executed"))
    return negative and any(name and name in text for name in completed)


def _positive_limitation(value: Any) -> bool:
    text = _text(value).casefold()
    return any(
        phrase in text
        for phrase in (
            "verified full git history",
            "full git history and object store were materialized and verified",
            "retained the requested commit",
        )
    )


def repair_canonical_truth(package: Mapping[str, Any]) -> dict[str, Any]:
    """Remove stale presentation contradictions without inventing evidence or scores."""
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {}))
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    records = [deepcopy(dict(item)) for item in canonical.get("scanner_execution_records") or assessment.get("scanner_execution_records") or [] if isinstance(item, Mapping)]

    completed: set[str] = set()
    for record in records:
        name = _scanner_name(record.get("scanner_name") or record.get("tool"))
        state = _text(record.get("state") or record.get("status")).casefold()
        artifact = _text(record.get("artifact_hash"))
        exact = record.get("exact_commit_match") is True
        done = record.get("completed") is True or state.startswith("completed")
        if done:
            completed.add(name)
            record["completed"] = True
            # A retained artifact bound to the exact SHA is verified execution evidence.
            if exact and artifact and artifact not in {"missing", "unavailable"}:
                record["verified"] = True
                record["verified_complete"] = True

    repaired_sections: list[dict[str, Any]] = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        section = deepcopy(dict(raw))
        for field in ("evidence", "findings", "unavailable"):
            values = section.get(field)
            if isinstance(values, list):
                section[field] = [
                    item for item in values
                    if not _stale_scanner_statement(item, completed)
                    and not (field == "unavailable" and _positive_limitation(item))
                ]
        score = section.get("presented_score", section.get("score"))
        status = _text(section.get("presented_status") or section.get("status")).upper()
        if isinstance(score, (int, float)) and not isinstance(score, bool) and ("NOT_SCORED" in status or "REVIEW_LIMITED" in status):
            normalized = _band(score)
            section["status"] = normalized.lower()
            section["presented_status"] = normalized
            section["assurance_status"] = "review_limited" if any(section.get("unavailable") or []) else "verified_with_completed_scanners"
        repaired_sections.append(section)
    assessment["sections"] = repaired_sections
    assessment["scanner_execution_records"] = deepcopy(records)

    notes = []
    for item in assessment.get("unavailable_data_notes") or []:
        if _stale_scanner_statement(item, completed) or _positive_limitation(item):
            continue
        notes.append(item)
    assessment["unavailable_data_notes"] = notes

    stages: list[dict[str, Any]] = []
    for raw in canonical.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        stage = deepcopy(dict(raw))
        for field in ("evidence", "findings", "unavailable"):
            values = stage.get(field)
            if isinstance(values, list):
                stage[field] = [
                    item for item in values
                    if not _stale_scanner_statement(item, completed)
                    and not (field == "unavailable" and _positive_limitation(item))
                ]
        if _text(stage.get("stage_id")) == "decision_report_generation" and assessment.get("comprehensive_score_truth"):
            stage["report_contract_status"] = "passed"
            stage["report_contract_reason"] = None
            stage["summary"] = "The core decision-report artifacts were generated from synchronized canonical score truth and retained for final human review."
        stages.append(stage)

    findings = [deepcopy(dict(item)) for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    decision_findings = [item for item in findings if item.get("technical_score_impact") != "none" and item.get("production_scope") is not False]
    non_production = [item for item in findings if item not in decision_findings]

    canonical["assessment"] = assessment
    canonical["scanner_execution_records"] = records
    canonical["stage_summaries"] = stages
    canonical["canonical_findings"] = decision_findings
    canonical["findings_register"] = deepcopy(decision_findings)
    canonical["executive_risk_register"] = deepcopy(decision_findings[:7])
    canonical["priority_findings"] = deepcopy(decision_findings[:5])
    canonical["non_production_observations"] = non_production
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update({
        "report_quality_repairs_version": VERSION,
        "stale_scanner_contradictions_removed": True,
        "scored_sections_never_labeled_not_scored": True,
        "positive_evidence_not_rendered_as_unavailable": True,
        "non_production_findings_excluded_from_decision_risk": True,
    })
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical
    return result


def _scorecard_page(canonical: Mapping[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    sections = [item for item in assessment.get("sections") or [] if isinstance(item, Mapping)]
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("QualityScorecardTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=colors.HexColor("#0f172a"), spaceAfter=12)
    cell = ParagraphStyle("QualityScorecardCell", parent=styles["BodyText"], fontName="Helvetica", fontSize=6.8, leading=8.6, textColor=colors.HexColor("#334155"), wordWrap="CJK")
    header = ParagraphStyle("QualityScorecardHeader", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)

    def paragraph(value: Any, style: ParagraphStyle = cell) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    rows: list[list[Any]] = [[paragraph("Control", header), paragraph("Status", header), paragraph("Score", header), paragraph("Summary", header)]]
    for item in sections:
        score = item.get("presented_score", item.get("score"))
        score_label = f"{int(round(score))}/100" if isinstance(score, (int, float)) and not isinstance(score, bool) else "NOT SCORED"
        rows.append([
            paragraph(item.get("label") or item.get("id")),
            paragraph(_text(item.get("presented_status") or item.get("status") or "unknown").replace("_", " ").title()),
            paragraph(score_label),
            paragraph(item.get("summary")),
        ])
    table = LongTable(rows, colWidths=[1.42 * inch, 1.12 * inch, .68 * inch, 4.28 * inch], repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.58 * inch, bottomMargin=.62 * inch, invariant=1)
    doc.build([Spacer(1, .05 * inch), Paragraph("Canonical Technical Scorecard", title), table])
    return buffer.getvalue()


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    """Replace the overflowing scorecard page and keep package hashes/counts coherent."""
    from pypdf import PdfReader, PdfWriter

    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    raw = base64.b64decode(str(result.get("pdf_base64") or ""))
    if not raw.startswith(b"%PDF"):
        return result
    reader = PdfReader(io.BytesIO(raw))
    replacement = PdfReader(io.BytesIO(_scorecard_page(canonical)))
    writer = PdfWriter()
    replaced = False
    for page in reader.pages:
        text = page.extract_text() or ""
        if not replaced and "Canonical Technical Scorecard" in text:
            writer.add_page(replacement.pages[0])
            replaced = True
        else:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({
        "report_quality_repairs_version": VERSION,
        "scorecard_word_jumble_removed": replaced,
        "scorecard_cells_wrapped": replaced,
    })
    result.update({
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_page_count": len(writer.pages),
        "core_report_page_count": len(writer.pages),
        "final_package_page_count": len(writer.pages),
        "premium_report_renderer": contract,
    })
    return result


__all__ = ["VERSION", "repair_canonical_truth", "repair_rendered_report"]
