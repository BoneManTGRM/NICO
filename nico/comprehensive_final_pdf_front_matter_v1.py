from __future__ import annotations

import base64
import hashlib
import io
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_pdf_front_matter.v1"
_PATCH_MARKER = "_nico_comprehensive_final_pdf_front_matter_v1"


def _replace_first_two_pages(pdf_bytes: bytes, replacement_bytes: bytes) -> bytes:
    """Replace, rather than overlay, the two customer-facing front-matter pages.

    The former overlay retained the old page text underneath the visible premium
    design. PDF extraction therefore exposed duplicate scores, product names, page
    counts, and delivery wording even when the page looked mostly correct. Replacing
    the page objects removes that stale text layer while preserving the remaining
    report and imported outline entries.
    """

    from pypdf import PdfReader, PdfWriter

    source = PdfReader(io.BytesIO(pdf_bytes))
    replacement = PdfReader(io.BytesIO(replacement_bytes))
    if len(source.pages) < 2 or len(replacement.pages) < 2:
        raise ValueError("Comprehensive final PDF requires two replacement front-matter pages")

    writer = PdfWriter()
    writer.add_page(replacement.pages[0])
    writer.add_page(replacement.pages[1])
    if len(source.pages) > 2:
        writer.append(source, pages=(2, len(source.pages)), import_outline=True)
    if source.metadata:
        writer.add_metadata({str(key): str(value) for key, value in source.metadata.items() if value is not None})

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _front_matter_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return " ".join((reader.pages[index].extract_text() or "") for index in range(min(2, len(reader.pages))))


def _repair_final_pdf(result: dict[str, Any]) -> dict[str, Any]:
    from nico.comprehensive_express_quality_v7 import _front_matter_overlay
    from pypdf import PdfReader

    package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
    encoded = str(package.get("pdf_base64") or "").strip()
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
    limitations = assessment.get("limitation_metrics") if isinstance(assessment.get("limitation_metrics"), dict) else {}
    generated_at = str(result.get("generated_at") or "")
    if not encoded or not identity or not generated_at:
        return result

    try:
        original = base64.b64decode(encoded, validate=True)
        page_count = len(PdfReader(io.BytesIO(original)).pages)
        replacement = _front_matter_overlay(identity, assessment, limitations, generated_at, page_count)
        repaired = _replace_first_two_pages(original, replacement)
        repaired_count = len(PdfReader(io.BytesIO(repaired)).pages)
        front_text = _front_matter_text(repaired)
    except Exception as exc:
        result["status"] = "blocked"
        result["reason"] = f"final_pdf_front_matter_repair_failed:{type(exc).__name__}"
        return result

    package["pdf_base64"] = base64.b64encode(repaired).decode("ascii")
    package["pdf_sha256"] = hashlib.sha256(repaired).hexdigest()
    package["pdf_page_count"] = repaired_count
    package["final_package_page_count"] = repaired_count

    quality = result.get("report_quality_contract") if isinstance(result.get("report_quality_contract"), dict) else {}
    quality.update(
        {
            "final_front_matter_version": VERSION,
            "front_matter_pages_replaced_not_overlaid": True,
            "pdf_page_count_matches_final_artifact": repaired_count == page_count,
            "pdf_page_count_label_matches_artifact": f"Final PDF pages: {repaired_count}" in front_text,
            "duplicate_front_matter_page_count_absent": front_text.count("Final PDF pages:") == 1,
            "stale_front_matter_page_total_absent": f"Page 1 of {repaired_count}" in front_text and f"Page 2 of {repaired_count}" in front_text,
            "customer_facing_front_matter_name_consistent": "NICO Unified Strategic Assessment" not in front_text,
        }
    )
    package["report_quality_contract"] = quality
    result["report_package"] = package
    result["report_quality_contract"] = quality
    return result


def install_comprehensive_final_pdf_front_matter_v1() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    current_build: Callable[..., dict[str, Any]] = report.build_comprehensive_report_package
    if getattr(current_build, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "front_matter_pages_replaced_not_overlaid": True,
            "final_page_count_reconciled": True,
        }

    @wraps(current_build)
    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _repair_final_pdf(current_build(*args, **kwargs))

    setattr(build, _PATCH_MARKER, True)
    report.build_comprehensive_report_package = build
    return {
        "status": "installed",
        "version": VERSION,
        "front_matter_pages_replaced_not_overlaid": True,
        "final_page_count_reconciled": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_replace_first_two_pages",
    "install_comprehensive_final_pdf_front_matter_v1",
]
