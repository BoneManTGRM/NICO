from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any

VERSION = "nico.comprehensive_authorized_report.v1"

_REPLACEMENTS = (
    (
        "APPROVED FINAL · HUMAN REVIEW RECORDED · DELIVERY CONTROLLED SEPARATELY",
        "AUTHORIZED FINAL · HUMAN REVIEW RECORDED · CLIENT DELIVERY AUTHORIZED",
    ),
    (
        "APPROVED FINAL | HUMAN REVIEW RECORDED | DELIVERY CONTROLLED SEPARATELY",
        "AUTHORIZED FINAL | HUMAN REVIEW RECORDED | CLIENT DELIVERY AUTHORIZED",
    ),
    (
        "APPROVED FINAL | HUMAN DECISION RECORDED | DELIVERY CONTROLLED SEPARATELY",
        "AUTHORIZED FINAL | HUMAN DECISION RECORDED | CLIENT DELIVERY AUTHORIZED",
    ),
    (
        "FINAL APROBADO · REVISIÓN HUMANA REGISTRADA · ENTREGA CONTROLADA POR SEPARADO",
        "FINAL AUTORIZADO · REVISIÓN HUMANA REGISTRADA · ENTREGA AL CLIENTE AUTORIZADA",
    ),
    ("DELIVERY CONTROLLED SEPARATELY", "CLIENT DELIVERY AUTHORIZED"),
    ("Delivery controlled separately", "Client delivery authorized"),
    ("Client delivery: Controlled separately", "Client delivery: Authorized"),
    ("ENTREGA CONTROLADA POR SEPARADO", "ENTREGA AL CLIENTE AUTORIZADA"),
    ("Entrega controlada por separado", "Entrega al cliente autorizada"),
    ("Entrega al cliente: Controlada por separado", "Entrega al cliente: Autorizada"),
)


def authorized_text(value: str, *, authorization_mode: str = "human") -> str:
    output = str(value or "")
    for previous, replacement in _REPLACEMENTS:
        output = output.replace(previous, replacement)
    if authorization_mode == "automated":
        for previous, replacement in (
            (
                "DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
                "AUTHORIZED FINAL · AUTOMATED VERIFICATION RECORDED · CLIENT DELIVERY AUTHORIZED",
            ),
            (
                "DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED",
                "AUTHORIZED FINAL | AUTOMATED VERIFICATION RECORDED | CLIENT DELIVERY AUTHORIZED",
            ),
            (
                "BORRADOR · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
                "FINAL AUTORIZADO · VERIFICACIÓN AUTOMATIZADA REGISTRADA · ENTREGA AL CLIENTE AUTORIZADA",
            ),
            ("HUMAN REVIEW RECORDED", "AUTOMATED VERIFICATION RECORDED"),
            ("HUMAN DECISION RECORDED", "AUTOMATED VERIFICATION RECORDED"),
            ("Human review recorded", "Automated verification recorded"),
            ("REVISIÓN HUMANA REGISTRADA", "VERIFICACIÓN AUTOMATIZADA REGISTRADA"),
        ):
            output = output.replace(previous, replacement)
    return output


def _certificate_pdf(
    *,
    run_id: str,
    repository: str,
    commit_sha: str,
    authorizer: str,
    authorizer_role: str,
    authorized_at: str,
    authorization_reason: str,
    source_pdf_sha256: str,
    authorization_mode: str = "human",
) -> bytes:
    from html import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title="NICO Comprehensive — Authorized Final",
        author="NICO",
        invariant=1,
    )
    automated = authorization_mode == "automated"
    rows = [
        ["Report status", "AUTHORIZED FINAL"],
        ["Client delivery", "AUTHORIZED"],
        ["Review mode", "AUTOMATED TECHNICAL ASSESSMENT" if automated else "HUMAN REVIEW"],
        ["Human reviewed", "NO" if automated else "YES"],
        ["Authorizer", authorizer],
        ["Authorizer role", authorizer_role],
        ["Authorized at", authorized_at],
        ["Run", run_id],
        ["Repository", repository],
        ["Commit", commit_sha],
        ["Approved source PDF SHA-256", source_pdf_sha256],
    ]
    table = Table(rows, colWidths=[155, 315])
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
        Paragraph(
            (
                "NICO Comprehensive — AUTHORIZED AUTOMATED TECHNICAL ASSESSMENT"
                if automated
                else "NICO Comprehensive — AUTHORIZED FINAL"
            ),
            styles["Title"],
        ),
        Paragraph("CLIENT DELIVERY AUTHORIZED", styles["Heading1"]),
        Paragraph("Delivery: Authorized", styles["Heading2"]),
        Paragraph("Client Delivery Authorization Certificate", styles["Heading2"]),
        Spacer(1, 10),
        Paragraph(
            (
                "SARA's independent logical verifier and NICO's deterministic artifact gates "
                "accepted the exact evidence-bound report under the disclosed automated-delivery policy. "
                "No human cybersecurity specialist reviewed or certified this report."
                if automated
                else
                "The named reviewer approved the exact evidence-bound report and the "
                "named delivery authorizer separately authorized this same artifact for client delivery."
            ),
            styles["BodyText"],
        ),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph("Authorization reason", styles["Heading3"]),
        Paragraph(escape(authorization_reason), styles["BodyText"]),
    ]
    document.build(story)
    return buffer.getvalue()


def build_authorized_report_pdf(
    source_pdf: bytes,
    *,
    identity: Mapping[str, Any],
    delivery_authorization: Mapping[str, Any],
    source_pdf_sha256: str,
    authorization_mode: str = "human",
) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

    if not source_pdf.startswith(b"%PDF"):
        raise ValueError("authorized_report_source_pdf_invalid")
    certificate = _certificate_pdf(
        run_id=str(identity.get("run_id") or ""),
        repository=str(identity.get("repository") or ""),
        commit_sha=str(identity.get("commit_sha") or ""),
        authorizer=str(delivery_authorization.get("authorizer_identity") or ""),
        authorizer_role=str(delivery_authorization.get("authorizer_role") or ""),
        authorized_at=str(delivery_authorization.get("authorized_at") or ""),
        authorization_reason=str(delivery_authorization.get("authorization_reason") or ""),
        source_pdf_sha256=source_pdf_sha256,
        authorization_mode=authorization_mode,
    )
    source_writer = PdfWriter(clone_from=io.BytesIO(source_pdf))
    for page in source_writer.pages:
        stream = ContentStream(page.get_contents(), source_writer)
        changed = False
        for operands, operator in stream.operations:
            if operator in {b"Tj", b"'", b'"'}:
                targets = operands
            elif operator == b"TJ" and operands:
                targets = operands[0]
            else:
                continue
            for index, operand in enumerate(targets):
                if isinstance(operand, TextStringObject):
                    original = str(operand)
                    updated = authorized_text(original, authorization_mode=authorization_mode)
                    normalized = original.strip().casefold()
                    if updated == original and normalized == "controlled":
                        updated = "Authorized"
                    elif updated == original and normalized == "controlada":
                        updated = "Autorizada"
                    if updated != original:
                        targets[index] = TextStringObject(updated)
                        changed = True
                elif isinstance(operand, ByteStringObject):
                    raw = bytes(operand)
                    for encoding in ("utf-8", "latin-1"):
                        try:
                            decoded = raw.decode(encoding)
                        except UnicodeDecodeError:
                            continue
                        updated = authorized_text(decoded, authorization_mode=authorization_mode)
                        if updated != decoded:
                            targets[index] = ByteStringObject(updated.encode(encoding))
                            changed = True
                        break
        if changed:
            page.replace_contents(stream)

    output = PdfWriter()
    for page in PdfReader(io.BytesIO(certificate)).pages:
        output.add_page(page)
    for page in source_writer.pages:
        output.add_page(page)
    output.add_metadata(
        {
            "/Title": (
                "NICO Comprehensive — Authorized Automated Technical Assessment"
                if authorization_mode == "automated"
                else "NICO Comprehensive — Authorized Final"
            ),
            "/Author": "NICO",
            "/Producer": "NICO deterministic delivery-authorized report finalizer",
        }
    )
    buffer = io.BytesIO()
    output.write(buffer)
    return buffer.getvalue()


__all__ = ["VERSION", "authorized_text", "build_authorized_report_pdf"]
