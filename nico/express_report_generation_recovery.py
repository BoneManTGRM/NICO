from __future__ import annotations

import base64
import binascii
import hashlib
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_report_generation_recovery.v4"
_PATCH_MARKER = "_nico_express_report_generation_recovery_v4"
_MAX_ATTEMPTS = 3
_REQUIRED_FORMATS = ("markdown", "html", "pdf_base64")
_PDF_EOF_SCAN_BYTES = 1024


def _reports(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("reports")
    return value if isinstance(value, dict) else {}


def _pdf_integrity(result: dict[str, Any]) -> dict[str, Any]:
    encoded = str(_reports(result).get("pdf_base64") or "").strip()
    if not encoded:
        return {"valid": False, "reason": "missing", "size_bytes": 0, "sha256": ""}
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return {"valid": False, "reason": "invalid_base64", "size_bytes": 0, "sha256": ""}

    digest = hashlib.sha256(decoded).hexdigest()
    if not decoded.startswith(b"%PDF-"):
        return {
            "valid": False,
            "reason": "invalid_pdf_signature",
            "size_bytes": len(decoded),
            "sha256": digest,
        }

    trailer_window = decoded[-_PDF_EOF_SCAN_BYTES:].rstrip(b"\x00\t\n\r\x0c ")
    if b"%%EOF" not in trailer_window:
        return {
            "valid": False,
            "reason": "missing_pdf_eof",
            "size_bytes": len(decoded),
            "sha256": digest,
        }

    return {
        "valid": True,
        "reason": "verified",
        "size_bytes": len(decoded),
        "sha256": digest,
    }


def _usable_formats(result: dict[str, Any]) -> bool:
    reports = _reports(result)
    text_ready = all(bool(str(reports.get(name) or "").strip()) for name in ("markdown", "html"))
    return text_ready and _pdf_integrity(result)["valid"] is True


def _missing_formats(result: dict[str, Any]) -> list[str]:
    reports = _reports(result)
    missing = [name for name in ("markdown", "html") if not str(reports.get(name) or "").strip()]
    if _pdf_integrity(result)["valid"] is not True:
        missing.append("pdf_base64")
    return missing


def _rebuild_terminal_payload(result: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    from nico import final_report_consistency

    output = deepcopy(result)
    original_status = output.get("status")
    try:
        core_rebuild = getattr(final_report_consistency, "_rebuild_reports")
        core_rebuild(output)
    except Exception as exc:
        output["status"] = original_status
        return output, f"{type(exc).__name__}: {exc}"
    output["status"] = original_status
    return output, None


def install_express_report_generation_recovery() -> dict[str, Any]:
    from nico.api import main as api_main
    from nico.scanner_redaction_type_safety import install_scanner_redaction_type_safety

    scanner_normalization = install_scanner_redaction_type_safety()
    current: Callable[[dict[str, Any]], dict[str, Any]] = api_main.finalize_express_result_consistency
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "scanner_output_normalization": scanner_normalization,
        }

    @wraps(current)
    def finalize_with_report_recovery(result: dict[str, Any]) -> dict[str, Any]:
        output = deepcopy(current(result))
        attempts = 1
        renderer_errors: list[str] = []
        while not _usable_formats(output) and attempts < _MAX_ATTEMPTS:
            output, renderer_error = _rebuild_terminal_payload(output)
            if renderer_error:
                renderer_errors.append(renderer_error)
            attempts += 1

        pdf_integrity = _pdf_integrity(output)
        evidence = output.get("report_generation_recovery")
        evidence = deepcopy(evidence) if isinstance(evidence, dict) else {}
        evidence.update(
            {
                "version": PATCH_VERSION,
                "attempts": attempts,
                "maximum_attempts": _MAX_ATTEMPTS,
                "same_run_continuation": True,
                "duplicate_assessment_started": False,
                "required_formats": list(_REQUIRED_FORMATS),
                "usable_report_artifacts": _usable_formats(output),
                "missing_formats": _missing_formats(output),
                "pdf_integrity": pdf_integrity,
                "renderer_errors": renderer_errors,
                "blocked_status_bypass_for_render_only": True,
                "scanner_output_normalization": scanner_normalization,
            }
        )
        output["report_generation_recovery"] = evidence

        if _usable_formats(output):
            output["status"] = "complete"
            output["report_generation_status"] = "complete"
            output["recovery_required"] = False
            output.pop("recovery_code", None)
            output.pop("report_format_error", None)
            return output

        output["status"] = "blocked"
        output["report_generation_status"] = "blocked_missing_usable_artifacts"
        output["report_format_error"] = (
            "Express report generation exhausted bounded recovery without usable "
            "Markdown, HTML, and structurally complete PDF artifacts."
        )
        output["recovery_required"] = True
        output["recovery_code"] = "express_report_generation_exhausted"
        output["human_review_required"] = True
        output["client_ready"] = False
        output["client_delivery_allowed"] = False
        return output

    setattr(finalize_with_report_recovery, _PATCH_MARKER, True)
    setattr(finalize_with_report_recovery, "_nico_previous", current)
    api_main.finalize_express_result_consistency = finalize_with_report_recovery
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "maximum_attempts": _MAX_ATTEMPTS,
        "same_run_only": True,
        "duplicate_assessment_started": False,
        "required_formats": list(_REQUIRED_FORMATS),
        "pdf_integrity_required": True,
        "pdf_eof_required": True,
        "blocked_status_bypass_for_render_only": True,
        "renderer_errors_recorded": True,
        "scanner_output_normalization": scanner_normalization,
        "fail_closed": True,
    }


__all__ = ["PATCH_VERSION", "install_express_report_generation_recovery"]
