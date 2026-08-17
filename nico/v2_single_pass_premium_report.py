from __future__ import annotations

import base64
import hashlib
import io
import unicodedata
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico.comprehensive_client_ready_projection_v1 import (
    APPROVAL_STATUS,
    DELIVERY_STATUS,
    REPORT_FINALITY,
)
from nico.v2_authoritative_premium_report import (
    _html_from_markdown,
    project_authoritative_canonical,
)
from nico.v2_authoritative_review_gate import ensure_authoritative_review_gate
from nico.v2_client_ready_truth_projection_v1 import project_client_ready_truth
from nico.v2_dark_branded_cover import apply_dark_branded_cover
from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs
from nico.v2_premium_evidence_appendix import rebuild_premium_client_artifacts_with_appendix

VERSION = "nico.v2.single-pass-premium-report.v2.1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _project(value: Mapping[str, Any]) -> dict[str, Any]:
    return project_client_ready_truth(project_authoritative_canonical(value))


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


def _sanitize_text(value: str) -> str:
    return "".join("-" if ord(char) == 0x7F else char for char in str(value or ""))


def _sanitize_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        clean = _sanitize_text(original)
        return (TextStringObject(clean), clean != original)
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        clean = original.replace(b"\x7f", b"-")
        return (ByteStringObject(clean), clean != original)
    return value, False


def _sanitize_pdf_control_glyphs(pdf: bytes) -> bytes:
    """Replace malformed extracted U+007F text glyphs without re-rendering layout."""
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        stream = ContentStream(page.get_contents(), writer)
        changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], operand_changed = _sanitize_operand(operands[0])
                changed = changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], operand_changed = _sanitize_operand(value)
                    changed = changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                text_index = -1
                operands[text_index], operand_changed = _sanitize_operand(operands[text_index])
                changed = changed or operand_changed
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    sanitized = output.getvalue()
    _assert_no_control_glyphs(sanitized)
    return sanitized


def _semantic_text(value: str) -> str:
    """Normalize extracted PDF text for robust bilingual semantic validation."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.casefold().split())


def _has_human_review_gate(extracted: str) -> bool:
    normalized = _semantic_text(extracted)
    exact_markers = (
        "human review and acceptance gate",
        "puerta de revision humana y aceptacion",
        "puerta de revision y aceptacion humana",
        "puerta de revision y entrega",
    )
    if any(marker in normalized for marker in exact_markers):
        return True

    review = "human review" in normalized or "revision humana" in normalized or "puerta de revision" in normalized
    acceptance = "acceptance gate" in normalized or "aceptacion" in normalized or "aprobacion" in normalized
    boundary = (
        "client delivery blocked" in normalized
        or "client delivery not authorized" in normalized
        or "entrega al cliente bloqueada" in normalized
        or "aprobacion humana pendiente" in normalized
    )
    return review and acceptance and boundary


def _validate_review_pdf(pdf: bytes, canonical: Mapping[str, Any]) -> int:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("single-pass premium renderer did not produce a valid PDF")
    _assert_no_control_glyphs(pdf)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    for required in (
        _text(identity.get("run_id")),
        _text(identity.get("commit_sha")),
    ):
        if required and required not in extracted:
            raise ValueError(f"review PDF omitted required identity text: {required}")

    if not _has_human_review_gate(extracted):
        raise ValueError("review PDF omitted the human review and acceptance gate")
    return len(reader.pages)


def rebuild_single_pass_premium_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render the premium review package once from authoritative canonical truth."""
    prepared = deepcopy(dict(package))
    canonical = _project(
        prepared.get("json") if isinstance(prepared.get("json"), Mapping) else {}
    )
    prepared["json"] = canonical

    result = deepcopy(rebuild_premium_client_artifacts_with_appendix(prepared))
    canonical = _project(
        result.get("json") if isinstance(result.get("json"), Mapping) else canonical
    )
    result["json"] = canonical

    spanish = _is_spanish(canonical)
    # English and Spanish now share the same premium presentation shell.
    # The cover renderer localizes visible copy while preserving the exact
    # canonical run/commit identity and all review/delivery boundaries.
    result = deepcopy(apply_dark_branded_cover(result))
    canonical = _project(
        result.get("json") if isinstance(result.get("json"), Mapping) else canonical
    )
    result["json"] = canonical

    markdown = ensure_authoritative_review_gate(
        str(result.get("markdown") or ""), canonical, spanish=spanish
    ).strip() + "\n"
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = (
        "Evaluación Técnica Integral NICO"
        if spanish
        else f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    )
    rendered_html = _html_from_markdown(markdown, title, spanish=spanish)

    pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
    pdf = _sanitize_pdf_control_glyphs(pdf)
    page_count = _validate_review_pdf(pdf, canonical)

    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update(
        {
            "version": VERSION,
            "single_pass_renderer": True,
            "premium_layout_is_intermediate_review_pdf": True,
            "canonical_system_is_sole_truth": True,
            "approved_cover_assembled_inside_compiler": True,
            "localized_premium_cover_assembled": spanish,
            "spanish_cover_preserved": False,
            "cross_language_presentation_shell_parity": True,
            "post_render_pdf_replacement_disabled": True,
            "review_pdf_control_glyph_validation": True,
            "review_pdf_identity_validation": True,
            "markdown_html_review_gate_preserved": True,
            "pdf_review_gate_verified_bilingually": True,
            "legacy_spanish_review_gate_heading_accepted": True,
            "semantic_review_gate_validation": True,
            "automated_draft_until_human_approval": True,
            "page_count": page_count,
        }
    )
    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update(
        {
            "version": VERSION,
            "authoritative_truth_projected_before_render": True,
            "single_review_pdf_generation": True,
            "page_count": page_count,
        }
    )
    result.update(
        {
            "json": canonical,
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
            "report_finality": REPORT_FINALITY,
            "approval_status": APPROVAL_STATUS,
            "delivery_status": DELIVERY_STATUS,
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
            "phase17_artifact_rebuild": phase17,
            "premium_report_renderer": contract,
        }
    )
    return result


__all__ = ["VERSION", "rebuild_single_pass_premium_artifacts"]
