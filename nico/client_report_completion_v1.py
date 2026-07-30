from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico.client_finding_remediation_register_v1 import (
    build_finding_remediation_register,
    finding_register_markdown,
    render_finding_register_pdf,
)
from nico.scanner_applicability_v1 import normalize_scanner_applicability_package
from nico.v2_authoritative_premium_report import _html_from_markdown
from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs
from nico.v2_single_pass_premium_report import _sanitize_pdf_control_glyphs

VERSION = "nico.client-report-completion.v3"
_REGISTER_HEADINGS = (
    "## Detailed Canonical Findings",
    "## Hallazgos canónicos detallados",
    "## Finding and Remediation Register",
    "## Registro de hallazgos y remediación",
)
_REGISTER_BOUNDARIES = (
    "## Delivery Status",
    "## Estado de entrega",
    "## Evidence Appendix",
    "## Apéndice de evidencia",
    "## Human Review and Acceptance Gate",
    "## Puerta de revisión y entrega",
    "## Puerta de revisión humana y aceptación",
)
_PROVENANCE_HEADINGS = ("### Scanner provenance", "### Procedencia de analizadores")
_CURRENT_PROVENANCE_HEADINGS = (
    "## Analyzer Applicability and Provenance",
    "## Procedencia y aplicabilidad de analizadores",
)
_PROVENANCE_PAGE_MARKERS = (
    "scanner provenance",
    "procedencia de analizadores",
    "analyzer applicability and provenance",
    "procedencia y aplicabilidad de analizadores",
)
_EVIDENCE_PAGE_MARKERS = ("evidence appendix", "apéndice de evidencia", "apendice de evidencia")
_REVIEW_PAGE_MARKERS = (
    "human review and acceptance gate",
    "puerta de revisión y entrega",
    "puerta de revision y entrega",
)
_STALE_EMPTY_FINDING_TEXT = "No structured item was retained."
_STALE_EMPTY_FINDING_REPLACEMENT = "Structured finding register retained below."


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or identity.get("report_language")
    ).casefold()
    return language.startswith("es")


def _remove_section(markdown: str, heading: str) -> str:
    start = markdown.find(heading)
    if start < 0:
        return markdown
    candidates = [markdown.find(boundary, start + len(heading)) for boundary in _REGISTER_BOUNDARIES]
    ends = [position for position in candidates if position >= 0]
    end = min(ends) if ends else len(markdown)
    return markdown[:start].rstrip() + "\n\n" + markdown[end:].lstrip()


def _remove_old_register(markdown: str) -> str:
    result = markdown
    for heading in _REGISTER_HEADINGS:
        while heading in result:
            result = _remove_section(result, heading)
    return result


def _remove_legacy_scanner_provenance(markdown: str) -> str:
    current_positions = [markdown.rfind(heading) for heading in _CURRENT_PROVENANCE_HEADINGS]
    current_positions = [position for position in current_positions if position >= 0]
    if current_positions:
        markdown = markdown[: min(current_positions)].rstrip() + "\n"

    positions: list[int] = []
    for heading in ("## Evidence Appendix", "## Apéndice de evidencia"):
        cursor = 0
        while True:
            position = markdown.find(heading, cursor)
            if position < 0:
                break
            positions.append(position)
            cursor = position + len(heading)
    for position in sorted(positions, reverse=True):
        tail = markdown[position:]
        if any(marker in tail for marker in _PROVENANCE_HEADINGS):
            return markdown[:position].rstrip() + "\n"
    return markdown


def _insert_register(markdown: str, register_markdown: str) -> str:
    positions = [markdown.find(marker) for marker in _REGISTER_BOUNDARIES]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return markdown.rstrip() + "\n\n" + register_markdown.strip() + "\n"
    position = min(positions)
    return (
        markdown[:position].rstrip()
        + "\n\n"
        + register_markdown.strip()
        + "\n\n"
        + markdown[position:].lstrip()
    )


def _scanner_records(canonical: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    applicable = canonical.get("scanner_execution_records") or assessment.get("scanner_execution_records") or []
    not_applicable = canonical.get("not_applicable_scanner_records") or assessment.get("not_applicable_scanner_records") or []
    return (
        [item for item in applicable if isinstance(item, Mapping)],
        [item for item in not_applicable if isinstance(item, Mapping)],
    )


def scanner_provenance_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    applicable, not_applicable = _scanner_records(canonical)
    completed = [item for item in applicable if item.get("completed") is True]
    incomplete = [item for item in applicable if item.get("completed") is not True]
    register = canonical.get("client_finding_remediation_register") if isinstance(canonical.get("client_finding_remediation_register"), Mapping) else {}
    register_summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}

    if spanish:
        lines = [
            "## Procedencia y aplicabilidad de analizadores",
            "",
            f"- Repositorio: {_text(identity.get('repository'))}",
            f"- Commit exacto: {_text(identity.get('commit_sha'))}",
            f"- ID de ejecución: {_text(identity.get('run_id'))}",
            f"- ID del libro de evidencia: {_text(identity.get('evidence_ledger_id'))}",
            f"- Analizadores solicitados: {len(applicable) + len(not_applicable)}",
            f"- Analizadores aplicables: {len(applicable)}",
            f"- Aplicables completados: {len(completed)}",
            f"- Aplicables incompletos: {len(incomplete)}",
            f"- No aplicables: {len(not_applicable)}",
            f"- Hallazgos con ubicación exacta: {int(register_summary.get('exact_source_code_finding_count') or 0)}",
            "",
            "### Procedencia de analizadores aplicables",
            "",
        ]
    else:
        lines = [
            "## Analyzer Applicability and Provenance",
            "",
            f"- Repository: {_text(identity.get('repository'))}",
            f"- Exact commit: {_text(identity.get('commit_sha'))}",
            f"- Run ID: {_text(identity.get('run_id'))}",
            f"- Evidence ledger ID: {_text(identity.get('evidence_ledger_id'))}",
            f"- Requested analyzers: {len(applicable) + len(not_applicable)}",
            f"- Applicable analyzers: {len(applicable)}",
            f"- Completed applicable analyzers: {len(completed)}",
            f"- Incomplete applicable analyzers: {len(incomplete)}",
            f"- Not-applicable analyzers: {len(not_applicable)}",
            f"- Exact-source findings: {int(register_summary.get('exact_source_code_finding_count') or 0)}",
            "",
            "### Applicable scanner provenance",
            "",
        ]

    if not applicable:
        lines.append("- No applicable analyzer records were retained." if not spanish else "- No se conservaron registros de analizadores aplicables.")
    for item in applicable:
        name = _text(item.get("scanner_name") or item.get("tool"))
        state = _text(item.get("state") or item.get("status"))
        verified = "yes" if item.get("verified") is True else "no"
        exact = "yes" if item.get("exact_commit_match") is True else "no"
        artifact = _text(item.get("artifact_hash")) or "missing"
        findings = len(item.get("findings") or [])
        reason = _text(item.get("failure_reason") or item.get("reason"))
        line = (
            f"- {name}: state={state}; verified={verified}; exact_sha={exact}; "
            f"findings={findings}; artifact_hash={artifact}"
        )
        if reason and item.get("completed") is not True:
            line += f"; reason={reason}"
        lines.append(line)

    lines.extend(
        [
            "",
            "### Analizadores no aplicables" if spanish else "### Not-applicable analyzers",
            "",
        ]
    )
    if not not_applicable:
        lines.append("- None." if not spanish else "- Ninguno.")
    for item in not_applicable:
        name = _text(item.get("scanner_name") or item.get("tool"))
        reason = _text(item.get("applicability_reason")) or "Repository technology mismatch."
        suffix = "No completion credit was awarded." if not spanish else "No se otorgó crédito de finalización."
        lines.append(f"- {name}: {reason} {suffix}")

    if incomplete:
        lines.extend(
            [
                "",
                "### Evidencia aplicable incompleta" if spanish else "### Incomplete applicable analyzer evidence",
                "",
            ]
        )
        for item in incomplete:
            name = _text(item.get("scanner_name") or item.get("tool"))
            reason = _text(item.get("failure_reason") or item.get("reason")) or "Complete exact-SHA evidence was not retained."
            lines.append(f"- {name}: {reason}")
    lines.extend(
        [
            "",
            (
                "Los analizadores no aplicables se conservan por separado; no cuentan como completados ni reducen la cobertura de los analizadores que sí aplican."
                if spanish
                else "Not-applicable analyzers are retained separately. They do not count as completed and do not reduce coverage for analyzers that actually apply to the repository."
            ),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _provenance_pdf(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    markdown = scanner_provenance_markdown(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "AnalyzerProvenanceHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#075985"),
        spaceAfter=12,
    )
    subheading = ParagraphStyle(
        "AnalyzerProvenanceSubheading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#075985"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "AnalyzerProvenanceBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.3,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    story: list[Any] = [Spacer(1, .2 * inch)]
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            story.append(Paragraph(html.escape(line[3:]), heading))
        elif line.startswith("### "):
            story.append(Paragraph(html.escape(line[4:]), subheading))
        elif line.startswith("- "):
            story.append(Paragraph("- " + html.escape(line[2:]), body))
        else:
            story.append(Paragraph(html.escape(line), body))
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.6 * inch,
        invariant=1,
        title="NICO Analyzer Applicability and Provenance",
        author="NICO",
    )
    document.build(story)
    return buffer.getvalue()


def _replace_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        replaced = original.replace(_STALE_EMPTY_FINDING_TEXT, _STALE_EMPTY_FINDING_REPLACEMENT)
        return TextStringObject(replaced), replaced != original
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        replaced = original.replace(
            _STALE_EMPTY_FINDING_TEXT.encode("latin-1"),
            _STALE_EMPTY_FINDING_REPLACEMENT.encode("latin-1"),
        )
        return ByteStringObject(replaced), replaced != original
    return value, False


def _replace_stale_pdf_text(pdf: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], operand_changed = _replace_operand(operands[0])
                changed = changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], operand_changed = _replace_operand(value)
                    changed = changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                operands[-1], operand_changed = _replace_operand(operands[-1])
                changed = changed or operand_changed
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _normalized_page_text(page: Any) -> str:
    return " ".join((page.extract_text() or "").casefold().split())


def _compose_pdf(base_pdf: bytes, register_pdf: bytes, provenance_pdf: bytes) -> bytes:
    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("client report completion requires a valid base PDF")
    base_reader = PdfReader(io.BytesIO(base_pdf))
    register_reader = PdfReader(io.BytesIO(register_pdf))
    provenance_reader = PdfReader(io.BytesIO(provenance_pdf))

    retained_pages: list[Any] = []
    insert_at: int | None = None
    for source_page in base_reader.pages:
        text = _normalized_page_text(source_page)
        if any(marker in text for marker in _PROVENANCE_PAGE_MARKERS):
            continue
        if insert_at is None and any(marker in text for marker in _EVIDENCE_PAGE_MARKERS):
            insert_at = len(retained_pages)
        retained_pages.append(source_page)

    if insert_at is None:
        for index, page in enumerate(retained_pages):
            text = _normalized_page_text(page)
            if any(marker in text for marker in _REVIEW_PAGE_MARKERS):
                insert_at = index
                break
    if insert_at is None:
        insert_at = len(retained_pages)

    writer = PdfWriter()
    for page in retained_pages[:insert_at]:
        writer.add_page(page)
    for page in register_reader.pages:
        writer.add_page(page)
    for page in retained_pages[insert_at:]:
        writer.add_page(page)
    for page in provenance_reader.pages:
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    combined = _replace_stale_pdf_text(output.getvalue())
    combined = _sanitize_pdf_control_glyphs(combined)
    _assert_no_control_glyphs(combined)
    return combined


def prepare_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    result = normalize_scanner_applicability_package(package)
    canonical = deepcopy(dict(result.get("json") or {}))
    register = build_finding_remediation_register(canonical)
    canonical["client_finding_remediation_register"] = register
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_report_completion_version": VERSION,
            "structured_finding_remediation_register": True,
            "exact_source_locations_required_for_code_findings": True,
            "scanner_not_applicable_separated_from_unavailable": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical
    result["client_finding_remediation_register"] = deepcopy(register)
    return result


def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    result = prepare_client_report_package(package)
    canonical = deepcopy(dict(result.get("json") or {}))
    register = canonical.get("client_finding_remediation_register")
    if not isinstance(register, Mapping):
        register = build_finding_remediation_register(canonical)
        canonical["client_finding_remediation_register"] = register
    spanish = _is_spanish(canonical)

    markdown = str(result.get("markdown") or "")
    markdown = _remove_old_register(markdown)
    markdown = _remove_legacy_scanner_provenance(markdown)
    markdown = markdown.replace(_STALE_EMPTY_FINDING_TEXT, _STALE_EMPTY_FINDING_REPLACEMENT)
    markdown = _insert_register(markdown, finding_register_markdown(register, spanish=spanish))
    markdown = markdown.rstrip() + "\n\n" + scanner_provenance_markdown(canonical, spanish=spanish).strip() + "\n"

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = (
        "Evaluación Técnica Integral NICO"
        if spanish
        else f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    )
    rendered_html = _html_from_markdown(markdown, title, spanish=spanish)

    base_pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
    register_pdf = render_finding_register_pdf(register, spanish=spanish)
    provenance_pdf = _provenance_pdf(canonical, spanish=spanish)
    pdf = _compose_pdf(base_pdf, register_pdf, provenance_pdf)
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    normalized_extracted = " ".join(extracted.casefold().split())
    compact_extracted = _compact(extracted)

    code_findings = [item for item in register.get("code_findings") or [] if isinstance(item, Mapping)]
    if code_findings and not any(
        marker in normalized_extracted
        for marker in (
            "finding and remediation register",
            "registro de hallazgos y remediacion",
            "registro de hallazgos y remediación",
        )
    ):
        raise ValueError("final client PDF omitted the Finding and Remediation Register")
    for item in code_findings[:60]:
        location = _text(item.get("location"))
        if location and _compact(location) not in compact_extracted:
            raise ValueError(f"final client PDF omitted exact source location: {location}")
    for item in canonical.get("not_applicable_scanner_records") or []:
        if not isinstance(item, Mapping):
            continue
        name = _text(item.get("scanner_name") or item.get("tool"))
        if name and name.casefold() not in normalized_extracted:
            raise ValueError(f"final client PDF omitted not-applicable analyzer: {name}")
    if _STALE_EMPTY_FINDING_TEXT.casefold() in normalized_extracted:
        raise ValueError("final client PDF retained the obsolete empty structured-finding message")

    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    completion = {
        "version": VERSION,
        "finding_register_in_json": True,
        "finding_register_in_markdown": True,
        "finding_register_in_html": True,
        "finding_register_in_pdf": True,
        "exact_source_locations_verified_in_pdf": True,
        "scanner_applicability_in_all_formats": True,
        "legacy_scanner_only_provenance_replaced": True,
        "obsolete_empty_finding_copy_removed": True,
        "secret_values_retained": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "page_count": page_count,
    }
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update(completion)
    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update(completion)

    result.update(
        {
            "json": canonical,
            "client_finding_remediation_register": deepcopy(register),
            "scanner_applicability": deepcopy(
                (canonical.get("assessment") or {}).get("scanner_applicability_summary") or {}
            ),
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
            "phase17_artifact_rebuild": phase17,
            "premium_report_renderer": contract,
            "client_report_completion": completion,
        }
    )
    return result


__all__ = [
    "VERSION",
    "finalize_client_report_package",
    "prepare_client_report_package",
    "scanner_provenance_markdown",
]
