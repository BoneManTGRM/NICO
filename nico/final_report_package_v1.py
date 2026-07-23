from __future__ import annotations

import base64
import io
import re
import threading
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator

VERSION = "nico.final_report_package.v1"
_EXPRESS_MARKER = "_nico_final_report_express_v1"
_COMPREHENSIVE_MARKER = "_nico_final_report_comprehensive_v1"
_REPORTLAB_LOCK = threading.RLock()

_FINAL_REPORT_STATE = "final_report_pending_human_approval"
_FINAL_BANNER = "FINAL REPORT PACKAGE · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED"

_TEXT_REPLACEMENTS = (
    (
        "DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED",
        _FINAL_BANNER,
    ),
    (
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
        "FINAL REPORT PACKAGE — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
    ),
    (
        "DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED",
        "FINAL REPORT PACKAGE - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED",
    ),
    (
        "DRAFT—HUMAN REVIEW REQUIRED • CLIENT DELIVERY BLOCKED",
        "FINAL REPORT PACKAGE—HUMAN REVIEW REQUIRED • CLIENT DELIVERY BLOCKED",
    ),
    (
        "DRAFT · HUMAN REVIEW REQUIRED",
        "FINAL REPORT PACKAGE · HUMAN REVIEW REQUIRED",
    ),
    (
        "DRAFT — HUMAN REVIEW REQUIRED",
        "FINAL REPORT PACKAGE — HUMAN REVIEW REQUIRED",
    ),
    (
        "DRAFT - HUMAN REVIEW REQUIRED",
        "FINAL REPORT PACKAGE - HUMAN REVIEW REQUIRED",
    ),
    (
        "The automated assessment is complete only as a draft.",
        "The automated final report package is complete and ready for human review.",
    ),
    (
        "review-only draft PDF",
        "final report package pending human approval",
    ),
    (
        "Download draft PDF",
        "Download final report",
    ),
)


def _final_language(value: Any) -> str:
    text = str(value or "")
    for source, replacement in _TEXT_REPLACEMENTS:
        text = text.replace(source, replacement)
    return text


def _final_filename(value: Any, service: str) -> str:
    filename = str(value or "").strip()
    if not filename:
        return f"nico-{service}-assessment-FINAL.pdf"
    filename = re.sub(r"(?i)([-_])DRAFT(?=\.pdf$)", r"\1FINAL", filename)
    filename = re.sub(r"(?i)draft(?=\.pdf$)", "FINAL", filename)
    if filename.lower().endswith(".pdf") and "final" not in filename.lower():
        filename = filename[:-4] + "-FINAL.pdf"
    return filename


def _report_state_fields() -> dict[str, Any]:
    return {
        "report_state": _FINAL_REPORT_STATE,
        "report_finalized": True,
        "human_review_status": "pending",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _finalize_report_mapping(value: Any, *, service: str) -> Any:
    if not isinstance(value, dict):
        return value
    output = value
    for key in ("markdown", "html", "delivery_status", "review_notice"):
        if isinstance(output.get(key), str):
            output[key] = _final_language(output[key])
    if "pdf_filename" in output or "pdf_base64" in output:
        output["pdf_filename"] = _final_filename(output.get("pdf_filename"), service)
    output.update(_report_state_fields())
    return output


def _finalize_comprehensive_output(output: Any) -> Any:
    if not isinstance(output, dict):
        return output
    output.update(_report_state_fields())
    for key in ("report_package", "reports"):
        if isinstance(output.get(key), dict):
            _finalize_report_mapping(output[key], service="comprehensive")
    stage_results = output.get("stage_results")
    if isinstance(stage_results, dict):
        for stage in stage_results.values():
            if not isinstance(stage, dict):
                continue
            for key in ("report_package", "reports"):
                if isinstance(stage.get(key), dict):
                    _finalize_report_mapping(stage[key], service="comprehensive")
    return output


def _sample_pdf_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.pages:
            return ""
        indexes = sorted({0, 1, 2, len(reader.pages) - 1})
        return "\n".join((reader.pages[index].extract_text() or "") for index in indexes)
    except Exception:
        return ""


def _pdf_contains_draft(pdf_bytes: bytes) -> bool:
    return bool(re.search(r"\bDRAFT\b", _sample_pdf_text(pdf_bytes), flags=re.IGNORECASE))


@contextmanager
def _final_reportlab_language() -> Iterator[None]:
    """Replace obsolete draft banners at render time without rewriting evidence."""

    with _REPORTLAB_LOCK:
        import reportlab.platypus as platypus
        from reportlab.pdfgen.canvas import Canvas

        original_paragraph = platypus.Paragraph
        original_methods: dict[str, Callable[..., Any]] = {}

        class FinalReportParagraph(original_paragraph):  # type: ignore[misc, valid-type]
            def __init__(self, text: Any, *args: Any, **kwargs: Any) -> None:
                super().__init__(_final_language(text), *args, **kwargs)

        platypus.Paragraph = FinalReportParagraph

        for method_name in ("drawString", "drawRightString", "drawCentredString", "drawAlignedString"):
            original = getattr(Canvas, method_name, None)
            if not callable(original):
                continue
            original_methods[method_name] = original

            def replacement(
                self: Any,
                x: Any,
                y: Any,
                text: Any,
                *args: Any,
                _original: Callable[..., Any] = original,
                **kwargs: Any,
            ) -> Any:
                return _original(self, x, y, _final_language(text), *args, **kwargs)

            setattr(Canvas, method_name, replacement)

        try:
            yield
        finally:
            platypus.Paragraph = original_paragraph
            for method_name, original in original_methods.items():
                setattr(Canvas, method_name, original)


def _install_express() -> dict[str, Any]:
    from nico import assessment_quality

    current = assessment_quality._build_polished_pdf_base64
    if getattr(current, _EXPRESS_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def final_express_report(result: dict[str, Any]) -> tuple[str | None, str | None]:
        with _final_reportlab_language():
            encoded, error = current(result)

        reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
        _finalize_report_mapping(reports, service="express")
        result["reports"] = reports
        result.update(_report_state_fields())
        result["final_report_package"] = {
            "version": VERSION,
            "service_id": "express",
            **_report_state_fields(),
        }

        if encoded and not error:
            try:
                pdf_bytes = base64.b64decode(encoded)
            except Exception:
                return None, "Final Express report PDF could not be decoded."
            if _pdf_contains_draft(pdf_bytes):
                return None, "Final Express report contract rejected an obsolete DRAFT banner."
        return encoded, error

    setattr(final_express_report, _EXPRESS_MARKER, True)
    setattr(final_express_report, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = final_express_report
    return {
        "status": "installed",
        "version": VERSION,
        "service_id": "express",
        "final_report_pending_human_approval": True,
    }


def _install_comprehensive() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report_module
    from nico import comprehensive_decision_grade_v5 as binding_module
    from nico import comprehensive_native_providers as providers

    current = providers.build_comprehensive_report_package
    if getattr(current, _COMPREHENSIVE_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def final_comprehensive_report(*args: Any, **kwargs: Any) -> dict[str, Any]:
        with _final_reportlab_language():
            output = current(*args, **kwargs)
        _finalize_comprehensive_output(output)

        package = output.get("report_package") if isinstance(output, dict) else None
        if isinstance(package, dict) and package.get("pdf_base64"):
            try:
                pdf_bytes = base64.b64decode(str(package["pdf_base64"]))
            except Exception:
                output["status"] = "blocked"
                output["reason"] = "final_comprehensive_pdf_decode_failed"
                package["pdf_error"] = "Final Comprehensive report PDF could not be decoded."
                package["pdf_base64"] = ""
                return output
            if _pdf_contains_draft(pdf_bytes):
                output["status"] = "blocked"
                output["reason"] = "obsolete_draft_banner_in_final_report"
                package["pdf_error"] = "Final Comprehensive report contract rejected an obsolete DRAFT banner."
                package["pdf_base64"] = ""
        return output

    setattr(final_comprehensive_report, _COMPREHENSIVE_MARKER, True)
    setattr(final_comprehensive_report, "_nico_previous", current)
    providers.build_comprehensive_report_package = final_comprehensive_report
    report_module.build_comprehensive_report_package = final_comprehensive_report
    binding_module.build_comprehensive_report_package = final_comprehensive_report
    return {
        "status": "installed",
        "version": VERSION,
        "service_id": "comprehensive",
        "final_report_pending_human_approval": True,
    }


def install_final_report_package_v1() -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "express": _install_express(),
        "comprehensive": _install_comprehensive(),
        "report_state": _FINAL_REPORT_STATE,
        "report_finalized": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_final_report_package_v1",
]
