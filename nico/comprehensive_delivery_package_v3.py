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

VERSION = "nico.comprehensive_approved_delivery.v3.1"
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


def _report_language(
    report_package: Mapping[str, Any],
    delivery_package: Mapping[str, Any] | None = None,
) -> str:
    delivery_manifest = (
        delivery_package.get("manifest")
        if isinstance(delivery_package, Mapping)
        and isinstance(delivery_package.get("manifest"), Mapping)
        else {}
    )
    canonical = (
        report_package.get("json")
        if isinstance(report_package.get("json"), Mapping)
        else {}
    )
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    language = _text(
        delivery_manifest.get("report_language")
        or report_package.get("report_language")
        or canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    )
    return language or "en"


def _is_spanish_language(report_language: str) -> bool:
    return _text(report_language).casefold().replace("_", "-").startswith("es")


def _certificate_page(
    accepted: Mapping[str, Any],
    *,
    report_language: str = "en",
) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    spanish = _is_spanish_language(report_language)
    review = accepted.get("review") if isinstance(accepted.get("review"), Mapping) else {}
    if spanish:
        rows = [
            ["Aprobación humana final", "APROBADA"],
            ["Autorización de entrega al cliente", "AUTORIZADA"],
            ["Revisor", _text(review.get("reviewer"))],
            ["Rol del revisor", _text(review.get("reviewer_role"))],
            ["Aprobado el", _text(review.get("decided_at"))],
            ["Motivo de la decisión", _text(review.get("reason"))],
            ["Digest del artefacto del informe", _text(accepted.get("report_artifact_digest"))],
            ["Manifiesto de la edición aceptada", _text(accepted.get("accepted_edition_manifest_sha256"))],
            ["Certificado de aprobación", _text(review.get("approval_certificate_sha256"))],
            ["Libro de trabajo de revisión", _text(accepted.get("review_work_ledger_sha256")) or "no aplicable a una ejecución heredada"],
            ["Fuente de evidencia de revisión", _text(accepted.get("review_work_source_sha256")) or "no aplicable a una ejecución heredada"],
        ]
        document_title = "NICO Comprehensive — Aprobación final y autorización de entrega al cliente"
        heading = "Aprobación final y autorización de entrega al cliente"
        introduction = (
            "Las páginas anteriores del informe constituyen el análisis NICO Comprehensive exacto "
            "revisado por una persona autorizada. Se inmovilizaron antes de autorizar la entrega al "
            "cliente. Esta página de certificado registra el estado autoritativo posterior a la "
            "revisión y la autorización de entrega sin regenerar ni modificar el análisis técnico."
        )
        boundary = (
            "El triaje técnico automatizado de NICO permanece separado de la disposición humana "
            "autorizada. La disposición humana permanece separada de la aprobación final del paquete. "
            "La entrega al cliente se autorizó únicamente después de superar el control protegido de "
            "aprobación final."
        )
    else:
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
        document_title = "NICO Comprehensive Final Approval and Client Delivery Authorization"
        heading = "Final Approval and Client Delivery Authorization"
        introduction = (
            "The preceding report pages are the exact human-reviewed Comprehensive analysis. "
            "They were frozen before client delivery authorization. This certificate page records "
            "the authoritative post-review approval and delivery state without regenerating or "
            "changing the technical analysis."
        )
        boundary = (
            "NICO automated technical triage remains distinct from authorized human disposition. "
            "Human disposition remains distinct from final package approval. Client delivery was "
            "authorized only after the protected final approval gate succeeded."
        )

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=document_title,
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
        Paragraph(heading, styles["Heading2"]),
        Spacer(1, 10),
        Paragraph(introduction, styles["BodyText"]),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph(boundary, styles["BodyText"]),
    ]
    doc.build(story)
    return buffer.getvalue()


def _append_certificate(
    pdf_bytes: bytes,
    certificate_page: bytes,
    *,
    report_language: str = "en",
) -> bytes:
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
    spanish = _is_spanish_language(report_language)
    writer.add_metadata(
        {
            "/Title": (
                "NICO Comprehensive — Entrega certificada"
                if spanish
                else "NICO Comprehensive"
            ),
            "/Author": "NICO",
            "/Producer": (
                "Entrega certificada de NICO Comprehensive"
                if spanish
                else "NICO certified Comprehensive delivery"
            ),
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
    report_language = _report_language(report_package, package)
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
    certified_pdf = _append_certificate(
        original_pdf,
        _certificate_page(accepted, report_language=report_language),
        report_language=report_language,
    )
    entries[_REPORT_PATH] = certified_pdf

    manifest = deepcopy(package.get("manifest") or {})
    manifest["artifact_schema"] = VERSION
    manifest["one_client_report"] = True
    manifest["client_pdf_count"] = 1
    manifest["final_human_approval_status"] = "approved"
    manifest["client_delivery_authorization_status"] = "authorized"
    manifest["approval_certificate_page_appended"] = True
    manifest["approval_certificate_language"] = report_language
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
        "approval_certificate_language": report_language,
        "report_analysis_regenerated_during_delivery_packaging": False,
        "human_review_required": True,
        "client_delivery_allowed": True,
    }


__all__ = ["VERSION", "build_comprehensive_delivery_package"]
