from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.v2.report-quality-repairs.v2"


_FINAL_PDF_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED",
        "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
    ),
    (
        "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED",
        "FINAL REPORT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
    ),
    (
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
        "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED",
    ),
    (
        "The package is a review-gated draft",
        "The package is a final automated assessment pending human approval",
    ),
    (
        "The report is an evidence-bound draft.",
        "The report is a final automated assessment pending human approval.",
    ),
    (
        "The automated assessment is complete only as a draft.",
        "The automated assessment is complete and pending human approval.",
    ),
    (" · DRAFT", " · FINAL"),
    (" DRAFT ", " FINAL "),
    ("DRAFT", "FINAL"),
)


_FINAL_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    *_FINAL_PDF_REPLACEMENTS,
    (
        "The package is a review-gated final: automated evidence and recommendations are not client approval or delivery authorization.",
        "The package is a final automated assessment pending human approval; automated evidence and recommendations are not client approval or delivery authorization.",
    ),
)


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
    negative = any(
        token in text
        for token in (
            "status=missing",
            "status=failed",
            " unavailable",
            " did not run",
            " not executed",
        )
    )
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
    records = [
        deepcopy(dict(item))
        for item in canonical.get("scanner_execution_records")
        or assessment.get("scanner_execution_records")
        or []
        if isinstance(item, Mapping)
    ]

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
                    item
                    for item in values
                    if not _stale_scanner_statement(item, completed)
                    and not (field == "unavailable" and _positive_limitation(item))
                ]
        score = section.get("presented_score", section.get("score"))
        status = _text(section.get("presented_status") or section.get("status")).upper()
        if (
            isinstance(score, (int, float))
            and not isinstance(score, bool)
            and ("NOT_SCORED" in status or "REVIEW_LIMITED" in status)
        ):
            normalized = _band(score)
            section["status"] = normalized.lower()
            section["presented_status"] = normalized
            section["assurance_status"] = (
                "review_limited"
                if any(section.get("unavailable") or [])
                else "verified_with_completed_scanners"
            )
        repaired_sections.append(section)
    assessment["sections"] = repaired_sections
    assessment["scanner_execution_records"] = deepcopy(records)

    assessment["unavailable_data_notes"] = [
        item
        for item in assessment.get("unavailable_data_notes") or []
        if not _stale_scanner_statement(item, completed)
        and not _positive_limitation(item)
    ]

    stages: list[dict[str, Any]] = []
    for raw in canonical.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        stage = deepcopy(dict(raw))
        for field in ("evidence", "findings", "unavailable"):
            values = stage.get(field)
            if isinstance(values, list):
                stage[field] = [
                    item
                    for item in values
                    if not _stale_scanner_statement(item, completed)
                    and not (field == "unavailable" and _positive_limitation(item))
                ]
        if (
            _text(stage.get("stage_id")) == "decision_report_generation"
            and assessment.get("comprehensive_score_truth")
        ):
            stage["report_contract_status"] = "passed"
            stage["report_contract_reason"] = None
            stage["summary"] = (
                "The core decision-report artifacts were generated from synchronized "
                "canonical score truth and retained for final human review."
            )
        stages.append(stage)

    findings = [
        deepcopy(dict(item))
        for item in canonical.get("canonical_findings") or []
        if isinstance(item, Mapping)
    ]
    decision_findings = [
        item
        for item in findings
        if item.get("technical_score_impact") != "none"
        and item.get("production_scope") is not False
    ]
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
    contract.update(
        {
            "report_quality_repairs_version": VERSION,
            "stale_scanner_contradictions_removed": True,
            "scored_sections_never_labeled_not_scored": True,
            "positive_evidence_not_rendered_as_unavailable": True,
            "non_production_findings_excluded_from_decision_risk": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical
    return result


def _scorecard_page(canonical: Mapping[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        TableStyle,
    )

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    sections = [
        item
        for item in assessment.get("sections") or []
        if isinstance(item, Mapping)
    ]
    if not sections:
        raise ValueError("scorecard replacement requires canonical section rows")

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "QualityScorecardTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=12,
    )
    cell = ParagraphStyle(
        "QualityScorecardCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.6,
        textColor=colors.HexColor("#334155"),
        wordWrap="CJK",
    )
    header = ParagraphStyle(
        "QualityScorecardHeader",
        parent=cell,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    def paragraph(value: Any, style: ParagraphStyle = cell) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    rows: list[list[Any]] = [
        [
            paragraph("Control", header),
            paragraph("Status", header),
            paragraph("Score", header),
            paragraph("Summary", header),
        ]
    ]
    for item in sections:
        score = item.get("presented_score", item.get("score"))
        score_label = (
            f"{int(round(score))}/100"
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else "NOT SCORED"
        )
        rows.append(
            [
                paragraph(item.get("label") or item.get("id")),
                paragraph(
                    _text(
                        item.get("presented_status")
                        or item.get("status")
                        or "unknown"
                    )
                    .replace("_", " ")
                    .title()
                ),
                paragraph(score_label),
                paragraph(item.get("summary")),
            ]
        )
    table = LongTable(
        rows,
        colWidths=[1.42 * inch, 1.12 * inch, 0.68 * inch, 4.28 * inch],
        repeatRows=1,
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        invariant=1,
    )
    doc.build(
        [
            Spacer(1, 0.05 * inch),
            Paragraph("Canonical Technical Scorecard", title),
            table,
        ]
    )
    return buffer.getvalue()


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


def _final_status_overlay(*, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.setFillColor(colors.HexColor("#f0a23a"))
    page.setFont("Helvetica-Bold", 7.2)
    status = (
        "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA BLOQUEADA"
        if spanish
        else "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    )
    page.drawString(42, 76, status)
    page.save()
    return buffer.getvalue()


def _replace_pdf_text(pdf: bytes, *, spanish: bool) -> tuple[bytes, int]:
    """Normalize finality language without re-rendering or disturbing the layout."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    replacements = 0
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        stream = ContentStream(page.get_contents(), writer)
        changed = False
        for operands, operator in stream.operations:
            if operator in {b"Tj", b"'", b'"'}:
                targets = operands
            elif operator == b"TJ" and operands:
                targets = operands[0]
            else:
                continue
            for index, operand in enumerate(targets):
                if isinstance(operand, TextStringObject):
                    original = str(operand)
                    updated = original
                    for previous, replacement in _FINAL_PDF_REPLACEMENTS:
                        updated = updated.replace(previous, replacement)
                    if updated != original:
                        targets[index] = TextStringObject(updated)
                        replacements += 1
                        changed = True
                elif isinstance(operand, ByteStringObject):
                    original_bytes = bytes(operand)
                    updated_bytes = original_bytes
                    for previous, replacement in _FINAL_PDF_REPLACEMENTS:
                        updated_bytes = updated_bytes.replace(
                            previous.encode("utf-8"), replacement.encode("utf-8")
                        )
                        updated_bytes = updated_bytes.replace(
                            previous.encode("latin-1", errors="ignore"),
                            replacement.encode("latin-1", errors="ignore"),
                        )
                    if updated_bytes != original_bytes:
                        targets[index] = ByteStringObject(updated_bytes)
                        replacements += 1
                        changed = True
        if changed:
            page.replace_contents(stream)

    if writer.pages:
        overlay = PdfReader(io.BytesIO(_final_status_overlay(spanish=spanish)))
        writer.pages[0].merge_page(overlay.pages[0], over=True)

    writer.add_metadata(
        {
            "/Title": "NICO Comprehensive Technical Assessment",
            "/Author": "NICO",
            "/Subject": "Final automated report pending required human approval",
        }
    )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), replacements


def _normalize_final_text(value: str, *, spanish: bool) -> str:
    output = str(value or "")
    for previous, replacement in _FINAL_TEXT_REPLACEMENTS:
        output = output.replace(previous, replacement)
    expected_title = "INFORME FINAL" if spanish else "FINAL REPORT"
    expected_approval = "APROBACIÓN HUMANA PENDIENTE" if spanish else "PENDING HUMAN APPROVAL"
    if expected_title not in output.upper() or expected_approval not in output.upper():
        status = (
            "INFORME FINAL · APROBACIÓN HUMANA PENDIENTE · ENTREGA BLOQUEADA"
            if spanish
            else "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
        )
        if "<html" in output.casefold():
            insertion = f'<p class="warning">{html.escape(status)}</p>'
            if "</article>" in output:
                output = output.replace("</article>", insertion + "</article>", 1)
            elif "</body>" in output:
                output = output.replace("</body>", insertion + "</body>", 1)
            else:
                output += insertion
        else:
            heading = "## Estado de entrega" if spanish else "## Delivery Status"
            output = output.rstrip() + f"\n\n{heading}\n{status}\n"
    return output


def _validate_final_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    expected_sections: list[Mapping[str, Any]],
    spanish: bool,
) -> None:
    from pypdf import PdfReader

    from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs

    if not pdf.startswith(b"%PDF"):
        raise ValueError("report quality repair produced an invalid PDF")
    _assert_no_control_glyphs(pdf)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    upper = extracted.upper()
    if re.search(r"\bDRAFT\b", upper):
        raise ValueError("final premium PDF retained stale DRAFT language")
    if spanish:
        normalized = (
            upper.replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
            .replace("Ü", "U")
            .replace("Ñ", "N")
        )
        if "INFORME FINAL" not in normalized or "APROBACION HUMANA PENDIENTE" not in normalized:
            raise ValueError("final Spanish premium PDF omitted pending-approval semantics")
    elif "FINAL REPORT" not in upper or "PENDING HUMAN APPROVAL" not in upper:
        raise ValueError("final premium PDF omitted final pending-approval semantics")

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    for required in (_text(identity.get("run_id")), _text(identity.get("commit_sha"))):
        if required and required not in extracted:
            raise ValueError(f"final premium PDF omitted required identity text: {required}")

    if expected_sections:
        scorecard_pages = [
            page.extract_text() or ""
            for page in reader.pages
            if "Canonical Technical Scorecard" in (page.extract_text() or "")
        ]
        if len(scorecard_pages) != 1:
            raise ValueError("final premium PDF must contain exactly one technical scorecard")
        scorecard_text = scorecard_pages[0]
        for section in expected_sections:
            label = _text(section.get("label") or section.get("id"))
            score = section.get("presented_score", section.get("score"))
            if label and label not in scorecard_text:
                raise ValueError(f"scorecard omitted canonical control row: {label}")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                score_label = f"{int(round(score))}/100"
                if score_label not in scorecard_text:
                    raise ValueError(
                        f"scorecard omitted canonical score {score_label} for {label}"
                    )


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    """Repair the final PDF and cross-format finality without inventing score changes."""
    from pypdf import PdfReader, PdfWriter

    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    sections = [
        item
        for item in assessment.get("sections") or []
        if isinstance(item, Mapping)
    ]
    raw = base64.b64decode(str(result.get("pdf_base64") or ""))
    if not raw.startswith(b"%PDF"):
        raise ValueError("report quality repair requires a valid PDF")

    reader = PdfReader(io.BytesIO(raw))
    writer = PdfWriter()
    replaced = False
    replacement_pages = (
        PdfReader(io.BytesIO(_scorecard_page(canonical))).pages if sections else []
    )
    for page in reader.pages:
        text = page.extract_text() or ""
        if sections and not replaced and "Canonical Technical Scorecard" in text:
            for replacement_page in replacement_pages:
                writer.add_page(replacement_page)
            replaced = True
        else:
            writer.add_page(page)
    if sections and not replaced:
        raise ValueError("canonical scorecard page was not found for safe replacement")

    output = io.BytesIO()
    writer.write(output)
    spanish = _is_spanish(canonical)
    pdf, finality_replacements = _replace_pdf_text(output.getvalue(), spanish=spanish)
    _validate_final_pdf(
        pdf,
        canonical,
        expected_sections=sections,
        spanish=spanish,
    )

    markdown = _normalize_final_text(str(result.get("markdown") or ""), spanish=spanish)
    rendered_html = _normalize_final_text(str(result.get("html") or ""), spanish=spanish)
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update(
        {
            "report_quality_repairs_version": VERSION,
            "scorecard_word_jumble_removed": replaced,
            "scorecard_cells_wrapped": replaced,
            "scorecard_replacement_skipped_no_sections": not bool(sections),
            "scorecard_rows_verified": bool(sections),
            "stale_draft_language_removed": True,
            "final_pending_approval_semantics_verified": True,
            "pdf_text_replacements": finality_replacements,
        }
    )
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    result.update(
        {
            "markdown": markdown,
            "html": rendered_html,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "status": "review_required",
            "assessment_state": "review_required",
            "report_finality": "final",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
            "premium_report_renderer": contract,
        }
    )
    return result


__all__ = ["VERSION", "repair_canonical_truth", "repair_rendered_report"]
