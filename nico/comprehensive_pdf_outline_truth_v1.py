from __future__ import annotations

import io
import sys
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

from nico import comprehensive_express_quality_v7 as quality

VERSION = "nico.comprehensive_pdf_outline_truth.v1"
_PATCH_MARKER = "_nico_comprehensive_pdf_outline_truth_v1"

_OUTLINE_HEADINGS = (
    ("Executive Decision Brief", "Executive Decision Brief"),
    ("Canonical Technical Scorecard", "Canonical Technical Scorecard"),
    ("Executive Risk Register", "Executive Risk Register"),
    ("Finding and Remediation Register", "Finding and Remediation Register"),
    ("Evidence Appendix", "Evidence Appendix"),
    ("Human Review and Acceptance Gate", "Human Review and Acceptance Gate"),
)


def _outline_targets(reader: PdfReader) -> list[tuple[str, int]]:
    targets: list[tuple[str, int]] = []
    if reader.pages:
        targets.append(("NICO Comprehensive", 0))

    found: set[str] = set()
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for title, marker in _OUTLINE_HEADINGS:
            if title in found or marker not in text:
                continue
            targets.append((title, index))
            found.add(title)
    return targets


def ensure_pdf_outline(pdf_bytes: bytes) -> bytes:
    """Retain imported bookmarks and add deterministic section navigation when absent."""

    if not pdf_bytes:
        return pdf_bytes
    reader = PdfReader(io.BytesIO(pdf_bytes))
    try:
        if len(reader.outline) > 0:
            return pdf_bytes
    except Exception:
        pass

    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    for title, page_index in _outline_targets(reader):
        writer.add_outline_item(title, page_index)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _wrap_counted(
    delegate: Callable[..., tuple[bytes, int]],
) -> Callable[..., tuple[bytes, int]]:
    if bool(getattr(delegate, _PATCH_MARKER, False)):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> tuple[bytes, int]:
        pdf_bytes, _ = delegate(*args, **kwargs)
        outlined = ensure_pdf_outline(pdf_bytes)
        return outlined, len(PdfReader(io.BytesIO(outlined)).pages)

    setattr(wrapped, _PATCH_MARKER, True)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def _wrap_single(delegate: Callable[..., bytes]) -> Callable[..., bytes]:
    if bool(getattr(delegate, _PATCH_MARKER, False)):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> bytes:
        return ensure_pdf_outline(delegate(*args, **kwargs))

    setattr(wrapped, _PATCH_MARKER, True)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def install_comprehensive_pdf_outline_truth_v1() -> dict[str, Any]:
    counted = _wrap_counted(quality.comprehensive_pdf_with_final_count)
    single = _wrap_single(quality.build_comprehensive_pdf)
    quality.comprehensive_pdf_with_final_count = counted
    quality.build_comprehensive_pdf = single

    report_module = sys.modules.get("nico.comprehensive_decision_grade_report_v5")
    if report_module is not None:
        setattr(report_module, "comprehensive_pdf_with_final_count", counted)

    return {
        "status": "installed",
        "version": VERSION,
        "counted_renderer_bound": quality.comprehensive_pdf_with_final_count is counted,
        "single_renderer_bound": quality.build_comprehensive_pdf is single,
        "existing_outline_preserved": True,
        "fallback_outline_added": True,
        "premium_visual_design_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "ensure_pdf_outline",
    "install_comprehensive_pdf_outline_truth_v1",
]
