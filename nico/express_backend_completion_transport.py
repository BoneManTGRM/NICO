from __future__ import annotations

import base64
import io
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

import nico.client_acceptance as client_acceptance
from nico.express_final_gate_completion_patch import normalize_assessment_completion

PATCH_VERSION = "nico.express_backend_completion_transport.v4"
_GATE_MARKER = "_nico_express_backend_completion_gate_v1"
_SAFE_MARKER = "_nico_express_backend_completion_safe_payload_v1"
_BUNDLE_MARKER = "_nico_express_backend_completion_bundle_v1"
_PDF_MARKER = "_nico_express_global_pdf_pagination_v2"
_COMPLETION_FIELDS = (
    "status",
    "current_stage",
    "progress_percent",
    "report_generation_status",
    "human_review_required",
    "client_ready",
    "client_delivery_allowed",
    "delivery_status",
    "assessment_completion",
    "express_completion",
    "reports",
    "sections",
    "maturity_signal",
    "technical_score",
)


def _copy_completion_fields(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(target)
    for field in _COMPLETION_FIELDS:
        if field in source:
            output[field] = deepcopy(source[field])
    return output


def _is_express(result: dict[str, Any]) -> bool:
    run_id = str(result.get("run_id") or "").strip().lower()
    tier = str(
        result.get("assessment_type")
        or result.get("service_tier")
        or result.get("assessment_mode")
        or ""
    ).strip().lower()
    return tier == "express" or run_id.startswith("express_run_")


def _paginate_express_pdf(pdf_bytes: bytes, result: dict[str, Any]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    if total_pages <= 0:
        raise ValueError("Express PDF contains no pages")

    locale = str(result.get("report_language") or result.get("language") or result.get("locale") or "en")
    page_label = "Página" if locale.lower().replace("_", "-").startswith("es") else "Page"
    writer = PdfWriter()

    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        footer_box = (
            width - 2.25 * inch,
            0.12 * inch,
            width - 0.42 * inch,
            0.48 * inch,
        )

        # Remove the previous footer from the PDF content stream, rather than
        # merely painting over it. This prevents stale totals such as
        # "Page 16 of 15" from remaining searchable/extractable in the final
        # client artifact.
        page.add_redact_annotation(footer_box, fill=(1, 1, 1))
        page.apply_redactions()

        overlay_buffer = io.BytesIO()
        overlay = canvas.Canvas(overlay_buffer, pagesize=(width, height), invariant=1)
        overlay.setFillColor(colors.HexColor("#64748b"))
        overlay.setFont("Helvetica", 7.1)
        overlay.drawRightString(width - 0.55 * inch, 0.3 * inch, f"{page_label} {index} of {total_pages}")
        overlay.save()
        overlay_buffer.seek(0)
        overlay_page = PdfReader(overlay_buffer).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    corrected = output.getvalue()
    if not corrected.startswith(b"%PDF-") or b"%%EOF" not in corrected[-2048:]:
        raise ValueError("Paginated Express PDF failed structural validation")

    verified = PdfReader(io.BytesIO(corrected))
    if len(verified.pages) != total_pages:
        raise ValueError("Paginated Express PDF page count changed unexpectedly")
    for index, page in enumerate(verified.pages, start=1):
        text = page.extract_text() or ""
        expected = f"{page_label} {index} of {total_pages}"
        if expected not in text:
            raise ValueError(f"Missing final pagination footer on page {index}")
        stale_footer = __import__("re").search(r"(?:Page|Página)\s+\d+\s+of\s+(?!%d\b)\d+" % total_pages, text)
        if stale_footer:
            raise ValueError(f"Stale pagination footer remains on page {index}: {stale_footer.group(0)}")
    return corrected


def _install_express_pdf_pagination() -> str:
    from nico import assessment_quality
    from nico.express_report_visual_qa_v16 import validate_express_pdf

    current_renderer = assessment_quality._build_polished_pdf_base64
    if getattr(current_renderer, _PDF_MARKER, False):
        return "already_installed"

    @wraps(current_renderer)
    def render_with_global_pagination(result: dict[str, Any]) -> tuple[str | None, str | None]:
        pdf_base64, error = current_renderer(result)
        if error or not pdf_base64 or not _is_express(result):
            return pdf_base64, error
        try:
            raw = base64.b64decode(pdf_base64, validate=True)
            corrected = _paginate_express_pdf(raw, result)
            total_pages = len(__import__("pypdf").PdfReader(io.BytesIO(corrected)).pages)
            result["express_pdf_pagination"] = {
                "status": "complete",
                "version": PATCH_VERSION,
                "page_count": total_pages,
                "global_page_numbers": True,
                "footer_total_matches_artifact": True,
                "stale_footer_content_removed": True,
            }
            qa = validate_express_pdf(corrected, result)
            result["express_visual_qa"] = qa
            reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
            reports["pdf_quality_status"] = qa.get("status")
            reports["pdf_quality_issues"] = list(qa.get("issues") or [])
            reports["client_delivery_allowed"] = bool(qa.get("client_delivery_allowed"))
            result["reports"] = reports
            result["client_delivery_allowed"] = False
            if qa.get("status") != "pass":
                result["client_delivery_block_reason"] = "Express visual QA did not pass."
            else:
                result["client_delivery_block_reason"] = "Authorized human review is still required."
            return base64.b64encode(corrected).decode("ascii"), None
        except Exception as exc:
            return None, f"Express global PDF pagination failed: {type(exc).__name__}: {exc}"

    setattr(render_with_global_pagination, _PDF_MARKER, True)
    setattr(render_with_global_pagination, "_nico_previous", current_renderer)
    assessment_quality._build_polished_pdf_base64 = render_with_global_pagination
    return "installed"


def install_express_backend_completion_transport() -> dict[str, Any]:
    """Bind the final Express PDF, bundle, completion, and safe-response transport.

    This installer runs after every renderer, quality gate, and compatibility
    installer. Exact Express runs must therefore be rebound here so a later
    installer cannot replace the bounded evidence-bundle path or the final PDF
    truth corrections before production execution.
    """

    from nico.api import main as api_main
    from nico.express_evidence_bundle_fast_path import attach_express_evidence_bundle

    pdf_status = _install_express_pdf_pagination()

    current_bundle: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_evidence_artifact_bundle
    bundle_status = "already_installed"
    if not getattr(current_bundle, _BUNDLE_MARKER, False):
        @wraps(current_bundle)
        def final_exact_run_bundle(result: dict[str, Any]) -> dict[str, Any]:
            if _is_express(result):
                output = dict(result)
                output.setdefault("assessment_type", "express")
                output.setdefault("service_tier", "express")
                return attach_express_evidence_bundle(output)
            return current_bundle(result)

        setattr(final_exact_run_bundle, _BUNDLE_MARKER, True)
        setattr(final_exact_run_bundle, "_nico_previous", current_bundle)
        api_main.attach_evidence_artifact_bundle = final_exact_run_bundle
        bundle_status = "installed"

    current_gate: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_client_acceptance_gate
    gate_status = "already_installed"
    if not getattr(current_gate, _GATE_MARKER, False):
        @wraps(current_gate)
        def authoritative_gate(result: dict[str, Any]) -> dict[str, Any]:
            before = deepcopy(result)
            after = current_gate(result)
            return normalize_assessment_completion(before, after)

        setattr(authoritative_gate, _GATE_MARKER, True)
        setattr(authoritative_gate, "_nico_previous", current_gate)
        api_main.attach_client_acceptance_gate = authoritative_gate
        client_acceptance.attach_client_acceptance_gate = authoritative_gate
        gate_status = "installed"

    current_safe: Callable[[dict[str, Any]], dict[str, Any]] = api_main.safe_assessment_response_payload
    safe_status = "already_installed"
    if not getattr(current_safe, _SAFE_MARKER, False):
        @wraps(current_safe)
        def preserve_completion_payload(result: dict[str, Any]) -> dict[str, Any]:
            normalized = normalize_assessment_completion(result, result)
            safe = current_safe(normalized)
            output = _copy_completion_fields(normalized, safe)
            completion = output.get("assessment_completion")
            if isinstance(completion, dict) and completion.get("status") == "complete_pending_human_review":
                output["status"] = "complete"
                output["current_stage"] = "complete"
                output["progress_percent"] = 100
                output["report_generation_status"] = "complete"
                output["human_review_required"] = True
                output["client_ready"] = False
                output["client_delivery_allowed"] = False
                output["delivery_status"] = "blocked_pending_human_review"
            return output

        setattr(preserve_completion_payload, _SAFE_MARKER, True)
        setattr(preserve_completion_payload, "_nico_previous", current_safe)
        api_main.safe_assessment_response_payload = preserve_completion_payload
        safe_status = "installed"

    statuses = {pdf_status, bundle_status, gate_status, safe_status}
    return {
        "status": "installed" if "installed" in statuses else "already_installed",
        "version": PATCH_VERSION,
        "pdf_pagination_binding": pdf_status,
        "bundle_binding": bundle_status,
        "gate_binding": gate_status,
        "safe_payload_binding": safe_status,
        "exact_run_identity_bound_last": True,
        "global_pdf_page_numbers_bound_last": True,
        "same_run_completion_persisted": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "_paginate_express_pdf",
    "install_express_backend_completion_transport",
]
