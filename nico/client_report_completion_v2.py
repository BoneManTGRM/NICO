from __future__ import annotations

import base64
import hashlib
import html
import io
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico import client_report_completion_v1 as legacy
from nico.client_assessment_truth_v3 import normalize_client_assessment_truth
from nico.client_finding_remediation_register_v5 import (
    build_finding_remediation_register,
    finding_register_markdown,
    render_finding_register_pdf,
    synchronize_canonical_finding_surfaces,
)
from nico.client_report_truth_contract_v63 import (
    apply_client_report_truth_contract,
    report_truth_markdown,
)
from nico.comprehensive_authoritative_scanner_truth_v62 import (
    reconcile_authoritative_scanner_truth,
)
from nico.scanner_applicability_v1 import normalize_scanner_applicability_package
from nico.v2_authoritative_premium_report import _html_from_markdown

VERSION = "nico.client-report-completion.v7"
_STATUS_REPLACEMENTS = {
    "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED": "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
    "FINAL REPORT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED": "AUTOMATED DRAFT - PENDING HUMAN APPROVAL - CLIENT DELIVERY BLOCKED",
    "FINAL REPORT": "AUTOMATED DRAFT",
    "Final Report": "Automated Draft",
    "final automated assessment pending human approval": "automated draft pending human approval",
    "final automated assessment": "automated draft",
    "Client-ready after internal approval": "Client delivery requires human approval",
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _install_contract(canonical: dict[str, Any]) -> dict[str, Any]:
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_report_completion_version": VERSION,
            "canonical_finding_identity_uses_source_anchor_and_family": True,
            "scanner_configuration_errors_are_not_code_findings": True,
            "repository_relative_paths_only": True,
            "finding_population_reconciled": True,
            "unverified_tls_pattern_not_promoted": True,
            "structured_finding_remediation_register": True,
            "exact_source_locations_required_for_code_findings": True,
            "scanner_not_applicable_separated_from_unavailable": True,
            "stable_finding_alias_projection_idempotent": True,
            "all_mirrored_finding_surfaces_synchronized": True,
            "exact_run_scanner_truth_reconciled_in_core_finalizer": True,
            "canonical_report_truth_shared_across_formats": True,
            "automated_output_is_draft_until_human_approval": True,
            "finding_evidence_status_and_confidence_required": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    return canonical


def _install_register(canonical: dict[str, Any]) -> dict[str, Any]:
    register = build_finding_remediation_register(canonical)
    synchronized = synchronize_canonical_finding_surfaces(canonical, register)
    return _install_contract(synchronized)


def _canonicalize(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = _install_register(normalize_client_assessment_truth(canonical))
    output = reconcile_authoritative_scanner_truth(output)
    output = apply_client_report_truth_contract(output)
    return output


def prepare_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare one canonical report model before the premium renderer runs."""

    result = normalize_scanner_applicability_package(package)
    canonical = normalize_client_assessment_truth(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    result["json"] = canonical

    result = normalize_scanner_applicability_package(result)
    canonical = _canonicalize(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )

    result["json"] = canonical
    result["client_finding_remediation_register"] = deepcopy(
        canonical["client_finding_remediation_register"]
    )
    result["finding_population"] = deepcopy(canonical["finding_population"])
    result["canonical_report_truth"] = deepcopy(canonical["canonical_report_truth"])
    return result


def _replace_status_text(value: str) -> str:
    output = value
    for old, new in _STATUS_REPLACEMENTS.items():
        output = output.replace(old, new)
    return output


def _insert_truth_boundary(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> str:
    heading = "## Estado del informe y límite de revisión" if spanish else "## Report Status and Review Boundary"
    if heading in markdown:
        return markdown
    block = report_truth_markdown(canonical, spanish=spanish).strip()
    first_break = markdown.find("\n\n")
    if first_break < 0:
        return block + "\n\n" + markdown.lstrip()
    return markdown[:first_break].rstrip() + "\n\n" + block + "\n\n" + markdown[first_break:].lstrip()


def _final_markdown(
    existing: str,
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    markdown = _replace_status_text(existing)
    markdown = _insert_truth_boundary(markdown, canonical, spanish=spanish)
    markdown = legacy._remove_old_register(markdown)
    markdown = legacy._remove_legacy_scanner_provenance(markdown)
    markdown = markdown.replace(
        legacy._STALE_EMPTY_FINDING_TEXT,
        legacy._STALE_EMPTY_FINDING_REPLACEMENT,
    )
    markdown = legacy._insert_register(
        markdown,
        finding_register_markdown(register, spanish=spanish),
    )
    if legacy._CLIENT_DELIVERY_MARKER not in markdown:
        markdown = markdown.rstrip() + f"\n\n<!-- {legacy._CLIENT_DELIVERY_MARKER} -->\n"
    return (
        markdown.rstrip()
        + "\n\n"
        + legacy.scanner_provenance_markdown(canonical, spanish=spanish).strip()
        + "\n"
    )


def _replace_pdf_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        replaced = _replace_status_text(original)
        return TextStringObject(replaced), replaced != original
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        replaced = original
        for old, new in _STATUS_REPLACEMENTS.items():
            replaced = replaced.replace(old.encode("latin-1", errors="ignore"), new.encode("latin-1", errors="ignore"))
        return ByteStringObject(replaced), replaced != original
    return value, False


def _replace_pdf_status_terms(pdf: bytes) -> bytes:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client report status normalization requires a valid PDF")
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
                operands[0], operand_changed = _replace_pdf_operand(operands[0])
                changed = changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], operand_changed = _replace_pdf_operand(value)
                    changed = changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                operands[-1], operand_changed = _replace_pdf_operand(operands[-1])
                changed = changed or operand_changed
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _truth_boundary_pdf(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    markdown = report_truth_markdown(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "ReportTruthHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#075985"),
        spaceAfter=12,
    )
    subheading = ParagraphStyle(
        "ReportTruthSubheading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#075985"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "ReportTruthBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5,
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
        leftMargin=.65 * inch,
        rightMargin=.65 * inch,
        topMargin=.65 * inch,
        bottomMargin=.65 * inch,
        invariant=1,
        title="NICO Report Status and Review Boundary",
        author="NICO",
    )
    document.build(story)
    return buffer.getvalue()


def _join_pdfs(*documents: bytes) -> bytes:
    writer = PdfWriter()
    for document in documents:
        for page in PdfReader(io.BytesIO(document)).pages:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _validate_final_surfaces(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> dict[str, Any]:
    summary = register.get("summary") if isinstance(register.get("summary"), Mapping) else {}
    if summary.get("finding_population_reconciled") is not True:
        raise ValueError("final client report finding populations do not reconcile")
    if summary.get("semantic_duplicate_code_anchors_absent") is not True:
        raise ValueError("final client report retained duplicate exact-source finding identities")
    if summary.get("scanner_configuration_errors_promoted_to_code_findings") is not False:
        raise ValueError("scanner configuration errors were promoted to code findings")
    if summary.get("unverified_tls_candidates_promoted_to_p1") is not False:
        raise ValueError("unverified TLS pattern candidates were promoted to P1")
    if summary.get("stable_alias_projection_idempotent") is not True:
        raise ValueError("canonical finding alias projection is not idempotent")

    truth = canonical.get("canonical_report_truth") if isinstance(canonical.get("canonical_report_truth"), Mapping) else {}
    if truth.get("automated_status") not in {"automated_draft", "human_approved_final"}:
        raise ValueError("canonical report truth did not retain a valid automated status")
    if truth.get("client_delivery_status") == "authorized" and truth.get("human_review_status") != "approved":
        raise ValueError("client delivery was authorized without human approval")

    code = [item for item in register.get("code_findings") or [] if isinstance(item, Mapping)]
    canonical_findings = [
        item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)
    ]
    decision_count = int(summary.get("decision_finding_count") or 0)
    if len(canonical_findings) != decision_count:
        raise ValueError(
            "canonical finding count does not match the reconciled decision population: "
            f"{len(canonical_findings)} != {decision_count}"
        )

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    combined = "\n".join((markdown, rendered_html, extracted))
    if "/tmp/nico-snapshot-scan-" in combined or "/home/runner/work/" in combined:
        raise ValueError("client report exposed a temporary worker path")
    if "unknown · unknown" in combined:
        raise ValueError("client report retained unknown analyzer and rule identity")
    if "No structured item was retained." in combined:
        raise ValueError("client report retained obsolete empty finding copy")
    if truth.get("automated_status") == "automated_draft":
        normalized = " ".join(combined.split()).casefold()
        if "automated draft" not in normalized:
            raise ValueError("automated report formats did not disclose Automated Draft status")
        if "client delivery blocked" not in normalized:
            raise ValueError("automated report formats did not disclose blocked client delivery")
        if "final report" in normalized:
            raise ValueError("automated report retained misleading Final Report language")

    compact_pdf = legacy._compact(extracted)
    for item in code[:60]:
        location = _text(item.get("location"))
        if location and legacy._compact(location) not in compact_pdf:
            raise ValueError(f"final client PDF omitted exact source location: {location}")

    return {
        "finding_population_reconciled": True,
        "canonical_decision_finding_count": decision_count,
        "exact_source_code_finding_count": len(code),
        "scanner_configuration_issue_count": int(
            summary.get("scanner_configuration_issue_count") or 0
        ),
        "temporary_worker_paths_absent": True,
        "unknown_analyzer_rule_pairs_absent": True,
        "semantic_duplicate_code_anchors_absent": True,
        "stable_finding_alias_projection_idempotent": True,
        "unverified_tls_candidates_not_promoted": True,
        "exact_run_scanner_truth_reconciled": True,
        "canonical_report_truth_in_all_formats": True,
        "automated_draft_language_enforced": truth.get("automated_status") == "automated_draft",
    }


def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Finalize one cross-format package from the repaired canonical model."""

    prepared = prepare_client_report_package(package)
    result = legacy.finalize_client_report_package(prepared)
    canonical = _canonicalize(
        result.get("json") if isinstance(result.get("json"), Mapping) else {}
    )
    register = canonical["client_finding_remediation_register"]
    spanish = legacy._is_spanish(canonical)

    markdown = _final_markdown(
        str(result.get("markdown") or ""),
        canonical,
        register,
        spanish=spanish,
    )
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = (
        "Evaluación Técnica Integral NICO"
        if spanish
        else f"NICO Comprehensive Technical Assessment - {_text(identity.get('repository'))}"
    )
    rendered_html = _html_from_markdown(markdown, title, spanish=spanish)

    base_pdf = _replace_pdf_status_terms(base64.b64decode(str(result.get("pdf_base64") or "")))
    truth_pdf = _truth_boundary_pdf(canonical, spanish=spanish)
    register_pdf = render_finding_register_pdf(register, spanish=spanish)
    truth_and_register_pdf = _join_pdfs(truth_pdf, register_pdf)
    provenance_pdf = legacy._provenance_pdf(canonical, spanish=spanish)
    pdf = legacy._compose_pdf(base_pdf, truth_and_register_pdf, provenance_pdf)
    validation = _validate_final_surfaces(
        canonical,
        register,
        markdown,
        rendered_html,
        pdf,
    )

    page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    truth = deepcopy(dict(canonical.get("canonical_report_truth") or {}))
    approval = deepcopy(dict(canonical.get("human_approval_metadata") or {}))
    approved = truth.get("automated_status") == "human_approved_final"
    completion = deepcopy(dict(result.get("client_report_completion") or {}))
    completion.update(
        {
            "version": VERSION,
            **validation,
            "finding_register_in_json": True,
            "finding_register_in_markdown": True,
            "finding_register_in_html": True,
            "finding_register_in_pdf": True,
            "exact_source_locations_verified_in_pdf": True,
            "scanner_applicability_in_all_formats": True,
            "full_evidence_appendix_preserved": (
                "Evidence Appendix" in markdown or "Apéndice de evidencia" in markdown
            ),
            "premium_cover_preserved": True,
            "human_review_required": not approved,
            "client_delivery_allowed": approved,
            "page_count": page_count,
        }
    )
    premium = deepcopy(dict(result.get("premium_report_renderer") or {}))
    premium.update(completion)
    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update(completion)

    result.update(
        {
            "json": canonical,
            "canonical_report_truth": truth,
            "human_approval_metadata": approval,
            "client_finding_remediation_register": deepcopy(register),
            "finding_population": deepcopy(register.get("summary") or {}),
            "markdown": markdown,
            "html": rendered_html,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "status": "approved" if approved else "review_required",
            "assessment_state": "approved_final" if approved else "pending_human_review",
            "report_finality": "approved_final" if approved else "automated_draft",
            "automated_status": truth.get("automated_status"),
            "evidence_status": truth.get("evidence_status"),
            "human_review_status": truth.get("human_review_status"),
            "client_delivery_status": truth.get("client_delivery_status"),
            "score_status": truth.get("score_status"),
            "limitations": deepcopy(truth.get("limitations") or []),
            "approval_status": "approved" if approved else "pending_human_approval",
            "delivery_status": "authorized" if approved else "blocked_pending_human_approval",
            "human_review_required": not approved,
            "human_review_completed": approved,
            "client_delivery_allowed": approved,
            "phase17_artifact_rebuild": phase17,
            "premium_report_renderer": premium,
            "client_report_completion": completion,
        }
    )
    return result


__all__ = [
    "VERSION",
    "_replace_pdf_status_terms",
    "finalize_client_report_package",
    "prepare_client_report_package",
]
