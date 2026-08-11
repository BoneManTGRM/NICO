from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_delivery_package_v2 import build_comprehensive_delivery_package as build_v2

VERSION = "nico.comprehensive_delivery_package.v3"
_REPORT_PATH = "01_nico_comprehensive_report.pdf"
_MANIFEST_PATH = "11_evidence_manifest.json"


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _certificate_page(accepted: Mapping[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    review = accepted.get("review") if isinstance(accepted.get("review"), Mapping) else {}
    rows = [
        ["Final human approval", "APPROVED"],
        ["Client-delivery authorization", "AUTHORIZED"],
        ["Reviewer", _text(review.get("reviewer"))],
        ["Reviewer role", _text(review.get("reviewer_role"))],
        ["Approved at", _text(review.get("decided_at"))],
        ["Decision reason", _text(review.get("reason"))],
        ["Report artifact digest", _text(accepted.get("report_artifact_digest"))],
        ["Accepted-edition manifest", _text(accepted.get("accepted_edition_manifest_sha256"))],
        ["Approval certificate", _text(review.get("approval_certificate_sha256"))],
        ["Review-work ledger", _text(accepted.get("review_work_ledger_sha256")) or "not applicable to legacy run"],
        ["Review evidence source", _text(accepted.get("review_work_source_sha256")) or "not applicable to legacy run"],
    ]
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title="NICO Comprehensive Final Approval and Client Delivery Authorization",
        invariant=1,
    )
    table = Table(rows, colWidths=[170, 290])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story = [
        Paragraph("NICO Comprehensive", styles["Title"]),
        Paragraph("Final Approval and Client Delivery Authorization", styles["Heading2"]),
        Spacer(1, 10),
        Paragraph(
            "The preceding report pages are the exact human-reviewed Comprehensive analysis. "
            "They were frozen before client delivery authorization. This certificate page records "
            "the authoritative post-review approval and delivery state without regenerating or "
            "changing the technical analysis.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph(
            "NICO automated technical triage remains distinct from authorized human disposition. "
            "Human disposition remains distinct from final package approval. Client delivery was "
            "authorized only after the protected final approval gate succeeded.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()


def _append_certificate(pdf_bytes: bytes, certificate_page: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter

    if not pdf_bytes.startswith(b"%PDF") or not certificate_page.startswith(b"%PDF"):
        raise ValueError("comprehensive_delivery_certificate_pdf_invalid")
    source = PdfReader(io.BytesIO(pdf_bytes))
    certificate = PdfReader(io.BytesIO(certificate_page))
    writer = PdfWriter()
    for page in source.pages:
        writer.add_page(page)
    for page in certificate.pages:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "NICO Comprehensive",
            "/Author": "NICO",
            "/Producer": "NICO certified Comprehensive delivery",
        }
    )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def build_comprehensive_delivery_package(
    report_package: Mapping[str, Any],
) -> dict[str, Any]:
    accepted = report_package.get("accepted_edition")
    if not isinstance(accepted, Mapping):
        raise ValueError("comprehensive_delivery_accepted_edition_required")
    review = accepted.get("review") if isinstance(accepted.get("review"), Mapping) else {}
    if (
        accepted.get("accepted_edition") is not True
        or accepted.get("client_delivery_allowed") is not True
        or _text(review.get("decision")).casefold() != "approved"
    ):
        raise ValueError("comprehensive_delivery_requires_approved_accepted_edition")

    package = build_v2(report_package)
    if package.get("status") != "approved_for_delivery":
        return package
    encoded = _text(package.get("zip_base64"))
    try:
        archive = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("comprehensive_delivery_zip_invalid") from exc

    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(archive), "r") as source:
        for name in source.namelist():
            if not name.endswith("/"):
                entries[name] = source.read(name)
    original_pdf = entries.get(_REPORT_PATH, b"")
    certified_pdf = _append_certificate(original_pdf, _certificate_page(accepted))
    entries[_REPORT_PATH] = certified_pdf

    manifest = deepcopy(package.get("manifest") or {})
    manifest["artifact_schema"] = VERSION
    manifest["one_client_report"] = True
    manifest["client_pdf_count"] = 1
    manifest["final_human_approval_status"] = "approved"
    manifest["client_delivery_authorization_status"] = "authorized"
    manifest["approval_certificate_page_appended"] = True
    manifest["report_analysis_regenerated_during_delivery_packaging"] = False
    manifest["client_delivery_allowed"] = True
    artifacts = []
    for item in manifest.get("artifacts") or []:
        if not isinstance(item, Mapping):
            continue
        candidate = deepcopy(dict(item))
        if _text(candidate.get("path")) == _REPORT_PATH:
            candidate["size_bytes"] = len(certified_pdf)
            candidate["sha256"] = _sha256(certified_pdf)
        artifacts.append(candidate)
    manifest["artifacts"] = artifacts
    entries[_MANIFEST_PATH] = _json_bytes(manifest)
    final_archive = _zip(entries)

    return {
        **package,
        "artifact_schema": VERSION,
        "zip_base64": base64.b64encode(final_archive).decode("ascii"),
        "zip_sha256": _sha256(final_archive),
        "zip_size_bytes": len(final_archive),
        "manifest": manifest,
        "one_client_report": True,
        "client_pdf_count": 1,
        "final_human_approval_status": "approved",
        "client_delivery_authorization_status": "authorized",
        "approval_certificate_page_appended": True,
        "report_analysis_regenerated_during_delivery_packaging": False,
        "human_review_required": True,
        "client_delivery_allowed": True,
    }


__all__ = ["VERSION", "build_comprehensive_delivery_package"]
