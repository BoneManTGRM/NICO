from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from copy import deepcopy
from typing import Any, Mapping

from nico.decision_grade_premium_delivery_v1 import build_premium_delivery_package

VERSION = "nico.comprehensive_delivery_package.v2"
_SINGLE_REPORT_PATH = "01_nico_comprehensive_report.pdf"
_LEGACY_PDF_PATHS = {
    "01_executive_decision_report.pdf",
    "02_detailed_technical_assessment.pdf",
    "03_evidence_appendix.pdf",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _zip(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def _manifest_entry(name: str, payload: bytes) -> dict[str, Any]:
    return {
        "path": name,
        "content_type": (
            "application/pdf"
            if name.endswith(".pdf")
            else "text/csv"
            if name.endswith(".csv")
            else "application/json"
        ),
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
    }


def build_comprehensive_delivery_package(
    report_package: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the existing approved package with exactly one client-facing PDF.

    The legacy packaging helper is retained for its supporting-artifact generation,
    then normalized to the single-product architecture. No executive, simplified,
    premium, appendix, or alternate client PDF survives this boundary.
    """

    legacy = build_premium_delivery_package(report_package)
    encoded = str(legacy.get("zip_base64") or "").strip()
    try:
        archive = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("comprehensive_delivery_legacy_zip_invalid") from exc
    if not archive.startswith(b"PK"):
        raise ValueError("comprehensive_delivery_legacy_zip_invalid")

    source_entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(archive), "r") as source:
        for name in source.namelist():
            if name.endswith("/"):
                continue
            source_entries[name] = source.read(name)

    detailed_pdf = source_entries.get("02_detailed_technical_assessment.pdf")
    if not detailed_pdf:
        try:
            detailed_pdf = base64.b64decode(
                str(report_package.get("pdf_base64") or ""),
                validate=True,
            )
        except Exception:
            detailed_pdf = b""
    if not detailed_pdf.startswith(b"%PDF"):
        raise ValueError("comprehensive_delivery_single_report_pdf_required")

    entries = {
        name: payload
        for name, payload in source_entries.items()
        if name not in _LEGACY_PDF_PATHS and name != "11_evidence_manifest.json"
    }
    entries[_SINGLE_REPORT_PATH] = detailed_pdf

    candidate_csv = str(report_package.get("candidate_register_csv") or "").encode("utf-8")
    if candidate_csv:
        entries["03_candidate_review_register.csv"] = candidate_csv
    evidence_csv = str(report_package.get("evidence_csv") or "").encode("utf-8")
    if evidence_csv:
        entries["04_evidence_register.csv"] = evidence_csv

    legacy_manifest = legacy.get("manifest") if isinstance(legacy.get("manifest"), Mapping) else {}
    approved = legacy.get("status") == "approved_for_delivery" and legacy.get("client_delivery_allowed") is True
    legacy_missing = [
        str(value)
        for value in legacy.get("missing_required_artifacts") or []
        if str(value) not in _LEGACY_PDF_PATHS
    ]
    missing = sorted(set(legacy_missing))
    if not entries.get(_SINGLE_REPORT_PATH):
        missing.append(_SINGLE_REPORT_PATH)

    manifest = {
        "artifact_schema": VERSION,
        "product": "NICO Comprehensive",
        "report_id": str(legacy.get("report_id") or ""),
        "repository": str(legacy_manifest.get("repository") or ""),
        "run_id": str(legacy_manifest.get("run_id") or ""),
        "report_language": str(legacy_manifest.get("report_language") or ""),
        "delivery_status": "approved_for_delivery" if approved and not missing else "blocked",
        "one_client_report": True,
        "client_pdf_count": 1,
        "alternate_client_pdfs": False,
        "artifacts": [_manifest_entry(name, payload) for name, payload in sorted(entries.items())],
        "missing_required_artifacts": missing,
        "human_review_required": True,
        "client_delivery_allowed": bool(approved and not missing),
    }
    entries["11_evidence_manifest.json"] = _json_bytes(manifest)
    final_archive = _zip(entries)

    repository = str(manifest.get("repository") or "repository")
    run_id = str(manifest.get("run_id") or legacy.get("report_id") or "run")
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", repository).strip("-") or "repository"
    filename = (
        f"nico-comprehensive-delivery-{safe_repo}-{run_id}-"
        f"{'APPROVED' if manifest['client_delivery_allowed'] else 'BLOCKED'}.zip"
    )
    return {
        "artifact_schema": VERSION,
        "status": "approved_for_delivery" if manifest["client_delivery_allowed"] else "blocked",
        "report_id": str(legacy.get("report_id") or ""),
        "filename": filename,
        "zip_base64": base64.b64encode(final_archive).decode("ascii"),
        "zip_sha256": _sha256(final_archive),
        "zip_size_bytes": len(final_archive),
        "artifact_count": len(entries),
        "manifest": manifest,
        "missing_required_artifacts": missing,
        "one_client_report": True,
        "client_pdf_count": 1,
        "human_review_required": True,
        "client_delivery_allowed": manifest["client_delivery_allowed"],
    }


__all__ = ["VERSION", "build_comprehensive_delivery_package"]
