from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico.v2_authoritative_premium_report import project_authoritative_canonical
from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs
from nico.v2_premium_evidence_appendix import rebuild_premium_client_artifacts_with_appendix

VERSION = "nico.v2.single-pass-premium-report.v2"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_pdf_string(value: Any) -> Any:
    """Replace only control-glyph list markers while preserving all other text."""
    if isinstance(value, TextStringObject):
        return TextStringObject(str(value).replace("\x7f", "-").replace("•", "-"))
    if isinstance(value, ByteStringObject):
        return ByteStringObject(bytes(value).replace(b"\x7f", b"-"))
    return value


def _sanitize_final_pdf_text(pdf: bytes) -> bytes:
    """Repair C1 glyphs in the already-finished premium PDF, without rerendering it."""
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()

    for page in reader.pages:
        contents = page.get_contents()
        if contents is not None:
            stream = ContentStream(contents, reader)
            repaired_operations: list[tuple[list[Any], bytes]] = []
            for operands, operator in stream.operations:
                repaired = list(operands)
                if operator in {b"Tj", b"'"} and repaired:
                    repaired[0] = _safe_pdf_string(repaired[0])
                elif operator == b'"' and len(repaired) >= 3:
                    repaired[2] = _safe_pdf_string(repaired[2])
                elif operator == b"TJ" and repaired and isinstance(repaired[0], list):
                    repaired[0] = [_safe_pdf_string(item) for item in repaired[0]]
                repaired_operations.append((repaired, operator))
            stream.operations = repaired_operations
            page.replace_contents(stream)
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _validate_final_pdf(pdf: bytes, canonical: Mapping[str, Any]) -> int:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("single-pass premium renderer did not produce a valid PDF")
    _assert_no_control_glyphs(pdf)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    for required in (
        _text(identity.get("run_id")),
        _text(identity.get("commit_sha")),
        "Human Review and Acceptance Gate",
    ):
        if required and required not in extracted:
            raise ValueError(f"final premium PDF omitted required identity or gate text: {required}")
    return len(reader.pages)


def rebuild_single_pass_premium_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render the mature premium report exactly once from authoritative canonical truth.

    The old premium compiler creates the complete client document. A bounded final-byte
    sanitation pass only replaces malformed control-glyph list markers; it does not
    regenerate pages, alter scores, or replace the premium layout.
    """
    prepared = deepcopy(dict(package))
    canonical = project_authoritative_canonical(
        prepared.get("json") if isinstance(prepared.get("json"), Mapping) else {}
    )
    prepared["json"] = canonical

    result = deepcopy(rebuild_premium_client_artifacts_with_appendix(prepared))
    canonical = project_authoritative_canonical(
        result.get("json") if isinstance(result.get("json"), Mapping) else canonical
    )
    result["json"] = canonical

    rendered_pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
    pdf = _sanitize_final_pdf_text(rendered_pdf)
    page_count = _validate_final_pdf(pdf, canonical)
    markdown = str(result.get("markdown") or "")
    rendered_html = str(result.get("html") or "")

    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update(
        {
            "version": VERSION,
            "single_pass_renderer": True,
            "old_premium_layout_is_client_pdf": True,
            "canonical_system_is_sole_truth": True,
            "post_render_pdf_replacement_disabled": True,
            "final_pdf_control_glyph_validation": True,
            "final_pdf_text_operator_sanitation": True,
            "final_pdf_identity_validation": True,
            "page_count": page_count,
        }
    )
    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update(
        {
            "version": VERSION,
            "authoritative_truth_projected_before_render": True,
            "single_final_pdf_generation": True,
            "page_count": page_count,
        }
    )
    result.update(
        {
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
        }
    )
    return result


__all__ = [
    "VERSION",
    "_sanitize_final_pdf_text",
    "rebuild_single_pass_premium_artifacts",
]
