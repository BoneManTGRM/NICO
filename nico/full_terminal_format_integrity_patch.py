from __future__ import annotations

import base64
import binascii
import hashlib
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

FULL_TERMINAL_FORMAT_INTEGRITY_VERSION = "nico.full_terminal_format_integrity.v2"
_PATCH_MARKER = "_nico_full_terminal_format_integrity_v2"
_REQUIRED_FORMATS = ("markdown", "html", "pdf")


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validated_pdf(value: Any) -> tuple[bool, str | None, int]:
    if not _non_empty(value):
        return False, None, 0
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError):
        return False, None, 0
    if not raw.startswith(b"%PDF-"):
        return False, None, len(raw)
    return True, hashlib.sha256(raw).hexdigest(), len(raw)


def install_full_terminal_format_integrity() -> dict[str, Any]:
    """Fail closed when a Full report package lacks valid required export formats."""
    from nico import full_assessment_idempotent_handlers as handlers

    current: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = handlers._reports_handler
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": FULL_TERMINAL_FORMAT_INTEGRITY_VERSION}

    @wraps(current)
    def reports_with_complete_format_set(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(current(context, outputs))
        if result.get("status") != "complete":
            return result

        package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
        formats = package.get("formats") if isinstance(package.get("formats"), dict) else {}
        pdf_valid, pdf_sha256, pdf_size_bytes = _validated_pdf(formats.get("pdf"))
        availability = {
            "markdown": _non_empty(formats.get("markdown")),
            "html": _non_empty(formats.get("html")),
            "pdf": pdf_valid and not _non_empty(package.get("pdf_error")),
        }
        missing = [name for name in _REQUIRED_FORMATS if not availability[name]]
        complete = not missing

        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        evidence = deepcopy(evidence)
        evidence["required_formats"] = list(_REQUIRED_FORMATS)
        evidence["missing_formats"] = missing
        evidence["format_equivalence_ready"] = complete
        evidence["available_formats"] = [name for name in _REQUIRED_FORMATS if availability[name]]
        evidence["pdf_signature_valid"] = pdf_valid
        evidence["pdf_sha256"] = pdf_sha256
        evidence["pdf_size_bytes"] = pdf_size_bytes
        result["evidence"] = evidence

        result["format_integrity"] = {
            "version": FULL_TERMINAL_FORMAT_INTEGRITY_VERSION,
            "required_formats": list(_REQUIRED_FORMATS),
            "missing_formats": missing,
            "format_equivalence_ready": complete,
            "availability": availability,
            "pdf_signature_valid": pdf_valid,
            "pdf_sha256": pdf_sha256,
            "pdf_size_bytes": pdf_size_bytes,
        }
        if missing:
            result["status"] = "limited"
            result["message"] = (
                "Full report generation finished without a complete valid export set. "
                "Missing or invalid required format(s): " + ", ".join(missing) + "."
            )
            result["report_format_error"] = result["message"]
        else:
            result.pop("report_format_error", None)
        return result

    setattr(reports_with_complete_format_set, _PATCH_MARKER, True)
    setattr(reports_with_complete_format_set, "_nico_previous", current)
    handlers._reports_handler = reports_with_complete_format_set
    return {
        "status": "installed",
        "version": FULL_TERMINAL_FORMAT_INTEGRITY_VERSION,
        "required_formats": list(_REQUIRED_FORMATS),
        "pdf_signature_required": True,
        "fail_closed": True,
    }


__all__ = ["FULL_TERMINAL_FORMAT_INTEGRITY_VERSION", "install_full_terminal_format_integrity"]
