"""Deterministic lifecycle-only view of a retained, valid operator approval.

The stored approval and original certified bytes are never replaced. The rendered
manifest binds the corrected export to that receipt and to the reviewed source.
Rendering is read-only: it creates neither a human decision nor delivery authority.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from copy import deepcopy
from functools import lru_cache
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_review_decision_v1 import report_package_from_record

VERSION = "nico.operator_approved_presentation.v1"
RECEIPT_VERSION = "nico.operator_approved_presentation.v2"


def _approval_record_rows(receipt: Mapping[str, Any], *, authorized: bool) -> list[tuple[str, Any]]:
    """Render the owned approval record from the validated detached receipt.

    Original/source hashes are labelled explicitly; none identifies these final
    bytes. Missing historical metadata stays missing rather than being invented.
    """
    identity = receipt["source_identity"]
    source = receipt["source_review_artifact_identity"]
    spanish = identity["report_language"] == "es-MX"
    def label(en, es):
        return es if spanish else en
    digests = source.get("artifact_digests", {})
    specialist = receipt.get("review_disclosure", {}).get("specialist_review_completed")
    rows = [
        (label("Reviewer identity", "Identidad del revisor"), receipt.get("reviewer")),
        (label("Reviewer role (metadata)", "Rol del revisor (metadatos)"), receipt.get("reviewer_role")),
        (label("Reviewer authorization", "Autorización del revisor"), label("Authenticated exact-edition approval", "Aprobación autenticada de la edición exacta")),
        (label("Review timestamp", "Fecha y hora de revisión"), receipt.get("decided_at")),
        (label("Decision", "Decisión"), label("Approved", "Aprobado")),
        (label("Client delivery", "Entrega al cliente"), label("Authorized", "Autorizada") if authorized else label("Not authorized", "No autorizada")),
        (label("Specialist review", "Revisión especializada"),
         label("Completed", "Completada") if specialist is True else label("Not completed", "No completada") if specialist is False else None),
        (label("Specialist risk acceptance", "Aceptación especializada del riesgo"), label("Separate decision; not made by this approval", "Decisión separada; no se realiza con esta aprobación")),
        (label("Run / reviewed revision", "Ejecución / revisión revisada"), f"{identity['run_id']} / {source['revision']}"),
        (label("Reviewed source PDF SHA-256", "SHA-256 PDF fuente revisado"), digests.get("pdf", {}).get("sha256")),
        (label("Reviewed canonical JSON SHA-256", "SHA-256 JSON canónico revisado"), digests.get("json", {}).get("sha256")),
        (label("Original certified PDF SHA-256", "SHA-256 PDF certificado original"), receipt.get("approved_artifact_digests", {}).get("pdf", {}).get("sha256")),
        (label("Approval receipt SHA-256 / record reference", "SHA-256 recibo de aprobación / referencia"), receipt.get("approval_certificate_sha256")),
        (label("Reviewer notes", "Notas del revisor"), receipt.get("reason")),
    ]
    return rows


def _approval_record_pdf(receipt: Mapping[str, Any], *, authorized: bool) -> bytes:
    from html import escape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
    spanish = receipt["source_identity"]["report_language"] == "es-MX"
    def label(en, es):
        return es if spanish else en
    missing = label("Not retained", "No conservado")
    rows = _approval_record_rows(receipt, authorized=authorized)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ApprovalRecordCell", parent=styles["BodyText"], fontSize=8, leading=10)
    p = lambda value: Paragraph(escape(str(value or missing)), body)
    table = Table([[p(k), p(v)] for k, v in rows], colWidths=[145, 387])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("GRID", (0, 0), (-1, -1), .3, "#cbd5e1"),
                              ("BACKGROUND", (0, 0), (0, -1), "#e0f2fe"),
                              ("TOPPADDING", (0, 0), (-1, -1), 5),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    stream = io.BytesIO()
    SimpleDocTemplate(stream, pagesize=(612, 792), leftMargin=40, rightMargin=40,
                      topMargin=40, bottomMargin=50, invariant=1).build([
        Paragraph(label("Operator Report Approval Record", "Registro de aprobación del operador"), styles["Title"]),
        table,
        p(label("The retained receipt binds this decision to the unchanged reviewed source. Final PDF bytes and their digest are bound separately in the detached edition manifest. Approval does not complete specialist review or transmit this report.",
                "El recibo conservado vincula la decisión con la fuente revisada sin cambios. Los bytes y el hash del PDF final se vinculan por separado en el manifiesto de la edición. La aprobación no completa la revisión especializada ni transmite el informe.")),
    ])
    return stream.getvalue()


def lifecycle_text(value: str) -> str:
    """Exact report lifecycle phrases only; never rewrite arbitrary pending work."""
    output = value
    boundary = "CLIENT DELIVERY BLOCKED" in value or "ENTREGA AL CLIENTE BLOQUEADA" in value
    for old, new in (
        ("AUTOMATED DRAFT", "OPERATOR APPROVED"),
        ("PENDING HUMAN APPROVAL", "SPECIALIST REVIEW SEPARATE"),
        ("HUMAN APPROVAL PENDING", "OPERATOR APPROVED"),
        ("HUMAN DECISION PENDING", "SPECIALIST REVIEW SEPARATE"),
        ("REVIEW PACKAGE READY", "APPROVED REPORT"),
        ("BORRADOR AUTOMATIZADO", "APROBADO POR OPERADOR"),
        ("APROBACIÓN HUMANA PENDIENTE", "REVISIÓN ESPECIALIZADA SEPARADA"),
        ("DECISIÓN HUMANA PENDIENTE", "REVISIÓN ESPECIALIZADA SEPARADA"),
        ("PAQUETE DE REVISIÓN LISTO", "INFORME APROBADO"),
        ("Client delivery remains blocked until explicit authorized human approval",
         "Client delivery remains blocked pending separate delivery authorization"),
        ("La entrega al cliente permanece bloqueada hasta la aprobación humana autorizada explícita",
         "La entrega al cliente sigue bloqueada; requiere autorización separada"),
        ("NICO generated an automated Comprehensive Technical Assessment draft", "NICO prepared this Comprehensive Technical Assessment"),
        ("NICO generó un borrador automatizado de Evaluación Técnica Integral", "NICO preparó esta Evaluación Técnica Integral"),
        ("it is not approval or client-delivery authorization", "operator approval is recorded; delivery remains unauthorized"),
        ("it is not approval or", "operator approval is recorded;"),
        ("The report is an evidence-bound draft.", "This report is operator-approved."),
        ("no constituye aprobación ni autorización de entrega", "tiene aprobación del operador; la entrega sigue sin autorización"),
        ("Human approval: Pending explicit reviewer action.", "Operator approval: Recorded; see certificate."),
        ("Human approval: Pending", "Operator approval: Approved"),
        ("Aprobación humana: Pendiente de una acción explícita del revisor.", "Aprobación del operador: Registrada; ver certificado."),
        ("Aprobación humana: Pendiente", "Aprobación del operador: Aprobado"),
        ("Registro de aprobación requerido", "Aprobación del operador registrada"),
        ("Registro de revisión humana y aprobación de artefactos exactos", "Registro de aprobación del operador"),
        ("Authorized human approval remains pending", "Specialist validation remains pending"),
        ("Approval state: pending_human_approval", "Operator approval: approved"),
        ("Review state: pending_human_approval", "Specialist review: pending"),
        ("Human Review and Exact-Artifact Approval", "Operator Report Approval"),
        ("Required approval record", "Recorded operator approval"),
        ("Automation cannot change this package to APPROVED FINAL or CLIENT DELIVERY AUTHORIZED.",
         "Operator approval is recorded. Automation alone cannot authorize client delivery."),
    ):
        if old in {
            "AUTOMATED DRAFT", "PENDING HUMAN APPROVAL", "HUMAN APPROVAL PENDING",
            "HUMAN DECISION PENDING", "REVIEW PACKAGE READY", "BORRADOR AUTOMATIZADO",
            "APROBACIÓN HUMANA PENDIENTE", "DECISIÓN HUMANA PENDIENTE", "PAQUETE DE REVISIÓN LISTO",
        } and not boundary:
            continue
        output = output.replace(old, new)
    # These are publication headers, not arbitrary occurrences in source evidence.
    output = re.sub(r"(NICO[^\n]*[|·\x01]\s*)automated draft", r"\1operator approved", output)
    if output.strip() == "client-delivery authorization.":
        output = output.replace("client-delivery authorization.", "delivery remains unauthorized.")
    if output.startswith("READ-ONLY"):
        output = output.replace("HUMAN REVIEW REQUIRED", "SPECIALIST REVIEW SEPARATE")
    if output.startswith("SOLO LECTURA"):
        output = output.replace("REVISIÓN HUMANA REQUERIDA", "REVISIÓN ESPECIALIZADA SEPARADA")
    return output


def delivery_lifecycle_text(value: str) -> str:
    for old, new in (
        ("CLIENT DELIVERY BLOCKED", "CLIENT DELIVERY AUTHORIZED"),
        ("ENTREGA AL CLIENTE BLOQUEADA", "ENTREGA AL CLIENTE AUTORIZADA"),
        ("APPROVED - DELIVERY BLOCKED", "APPROVED - DELIVERY AUTHORIZED"),
        ("SEPARATE AUTHORIZATION", "AUTHORIZATION RECORDED"),
        ("Client delivery remains blocked pending separate delivery authorization", "Client delivery authorized; specialist review remains separate"),
        ("La entrega al cliente sigue bloqueada; requiere autorización separada", "Entrega autorizada; revisión especializada separada"),
        ("client delivery remains blocked", "client delivery is authorized"),
        ("Client-delivery state: blocked", "Client-delivery state: authorized"),
        ("Client delivery: Not authorized.", "Client delivery: Authorized."),
        ("Client delivery: Blocked", "Client delivery: Authorized"),
        ("Entrega al cliente: No autorizada.", "Entrega al cliente: Autorizada."),
        ("Entrega al cliente: Bloqueada", "Entrega al cliente: Autorizada"),
        ("delivery remains unauthorized", "delivery authorization is recorded"),
        ("la entrega sigue sin autorización", "la entrega está autorizada"),
    ):
        value = value.replace(old, new)
    return value


@lru_cache(maxsize=4)
def _render_source(pdf: bytes, *, client_delivery_authorized: bool = False,
                   repair_current_truth: bool = False,
                   resolve_approval_references: bool = False,
                   approval_receipt_json: str = "") -> tuple[bytes, tuple[tuple[int, str, str], ...]]:
    writer = PdfWriter(clone_from=io.BytesIO(pdf))
    changes: list[tuple[int, str, str]] = []
    approval_page = None
    if resolve_approval_references:
        for index, candidate in enumerate(writer.pages):
            lines = (candidate.extract_text() or "").splitlines()
            if any(title in " ".join(lines[:6]) for title in (
                    "Human Review and Exact-Artifact Approval", "Operator Report Approval Record",
                    "Registro de revisión humana y aprobación de artefactos exactos", "Registro de aprobación del operador")):
                approval_page = index + 1
        if approval_page is None:
            raise ValueError("operator_approval_reference_target_missing")
    from nico.comprehensive_human_evidence_appendix import is_literal_evidence_page
    for page_index, page in enumerate(writer.pages):
        text = page.extract_text() or ""
        if repair_current_truth and is_literal_evidence_page(page):
            # These are source statements, including possibly quoted lifecycle
            # labels. Finalization must not rewrite them as report authority.
            continue
        cover = page_index == 0 and ("Executive posture" in text or "Postura ejecutiva" in text)
        approval_record = ("Human Review and Exact-Artifact Approval" in text and "Reviewer identity" in text
                           or "Identidad del revisor" in text and "Registro de aprobación requerido" in text)
        if approval_record and approval_receipt_json:
            from pypdf.generic import NameObject
            from nico.comprehensive_manifest_navigation_v1 import _page_overlay
            replacement = PdfReader(io.BytesIO(_approval_record_pdf(
                json.loads(approval_receipt_json), authorized=client_delivery_authorized)))
            if len(replacement.pages) != 1 or list(page.mediabox) != list(replacement.pages[0].mediabox):
                raise ValueError("operator_approval_record_pagination_mismatch")
            rendered = replacement.pages[0]
            page[NameObject("/Resources")] = rendered["/Resources"].clone(writer)
            page.replace_contents(rendered.get_contents().clone(writer))
            page.merge_page(PdfReader(io.BytesIO(_page_overlay(page_index + 1, len(writer.pages)))).pages[0])
            changes.append((page_index + 1, text, page.extract_text()))
            continue
        review_truth = repair_current_truth and (
            "Human Review and Approval Truth" in text
            or "Verdad de revisión humana y aprobación" in text
        )
        stream = ContentStream(page.get_contents(), writer)
        previous = ""
        phase_approval = False
        for operands, operator in stream.operations:
            if operator not in {b"Tj", b"TJ", b"'", b'"'}:
                continue
            targets = operands[0] if operator == b"TJ" else operands
            for index, operand in enumerate(targets):
                if not isinstance(operand, (TextStringObject, ByteStringObject)):
                    continue
                original = str(operand) if isinstance(operand, TextStringObject) else bytes(operand).decode("latin-1")
                updated = lifecycle_text(original)
                if resolve_approval_references:
                    updated = updated.replace("Recorded; see certificate.", f"Approved; record: report p. {approval_page}.")
                    updated = updated.replace("Registrada; ver certificado.", f"Aprobada; registro: pág. {approval_page} del informe.")
                normalized = original.strip()
                if review_truth:
                    if previous in {"Final human approval", "Aprobación humana final"} and normalized.upper() in {"PENDING", "PENDIENTE"}:
                        updated = "APPROVED" if previous == "Final human approval" else "APROBADA"
                    if client_delivery_authorized and previous in {"Client-delivery authorization", "Autorización de entrega al cliente"} and normalized.upper() in {"BLOCKED", "BLOQUEADA", "PENDING_AUTHORIZATION"}:
                        updated = "AUTHORIZED" if previous == "Client-delivery authorization" else "AUTORIZADA"
                if cover:
                    if normalized in {"HUMAN REVIEW", "REVISIÓN HUMANA"}:
                        updated = "OPERATOR APPROVAL" if normalized == "HUMAN REVIEW" else "APROBACIÓN OPERADOR"
                    elif previous == "HUMAN REVIEW" and normalized == "Pending":
                        updated = "Approved"
                    elif previous == "REVISIÓN HUMANA" and normalized == "Pendiente":
                        updated = "Aprobado"
                if normalized == "BLOCKED - AUTHORIZED HUMAN APPROVAL":
                    updated, phase_approval = "APPROVED - DELIVERY BLOCKED", True
                elif phase_approval and normalized == "REQUIRED":
                    updated, phase_approval = "SEPARATE AUTHORIZATION", False
                if approval_record and normalized.casefold() == "pending":
                    if previous == "Decision":
                        updated = "Approved"
                    elif previous in {"Reviewer identity", "Reviewer role", "Reviewer authorization", "Review timestamp", "Approval record ID"}:
                        updated = "See certificate"
                    elif previous == "Reviewer notes":
                        updated = "Optional"
                    # Residual-risk acceptance remains pending, with no fabricated work.
                if approval_record and normalized.casefold() == "pendiente":
                    if previous == "Decisión":
                        updated = "Aprobado"
                    elif previous in {"Identidad del revisor", "Rol del revisor", "Autorización del revisor",
                                      "Fecha y hora de revisión", "Marca de tiempo de la revisión", "ID del registro de aprobación"}:
                        updated = "Ver certificado"
                    elif previous == "Notas del revisor":
                        updated = "Opcionales"
                if approval_record and normalized == "Residual-risk acceptance":
                    updated = "Specialist risk acceptance"
                if approval_record:
                    for old, new in (
                        ("Approved PDF SHA-256", "Original certified PDF SHA-256"),
                        ("Recorded in detached approval receipt after decision", "Retained in original approval receipt"),
                        ("digests. Any regeneration, score change, finding change, candidate disposition change, evidence change, or artifact replacement",
                         "digests. Any score, finding, candidate disposition or evidence change invalidates this approval."),
                        ("creates a new draft and invalidates prior approval.",
                         "Lifecycle-only presentation corrections retain the original decision and a separate artifact binding."),
                    ):
                        updated = updated.replace(old, new)
                if client_delivery_authorized:
                    updated = delivery_lifecycle_text(updated)
                    if cover and previous == "CLIENT DELIVERY" and normalized == "Blocked":
                        updated = "Authorized"
                    elif cover and previous == "ENTREGA AL CLIENTE" and normalized == "Bloqueada":
                        updated = "Autorizada"
                if updated != original:
                    targets[index] = (TextStringObject(updated) if isinstance(operand, TextStringObject)
                                      else ByteStringObject(updated.encode("latin-1")))
                    changes.append((page_index + 1, original, updated))
                previous = normalized
        if any(change[0] == page_index + 1 for change in changes):
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), tuple(changes)


def render_operator_presentation(record: Mapping[str, Any], edition: Mapping[str, Any]) -> dict[str, Any]:
    """Call only with the current validated operator edition (or its rendered view)."""
    source = report_package_from_record(record)
    receipt_bound = source.get("json", {}).get("operator_approval_record_schema") == RECEIPT_VERSION
    version = RECEIPT_VERSION if receipt_bound else VERSION
    if edition.get("rendering_derivation", {}).get("version") == version:
        return dict(edition)
    from nico.comprehensive_operator_approval_v1 import _artifact_digests, _cover

    source_pdf = base64.b64decode(source["pdf_base64"], validate=True)
    source_hash = hashlib.sha256(source_pdf).hexdigest()
    if source_hash != edition["source_review_artifact_identity"]["artifact_digests"]["pdf"]["sha256"]:
        raise ValueError("operator_presentation_source_mismatch")
    corrected, changes = _render_source(source_pdf,
        resolve_approval_references=source.get("json", {}).get("reader_reference_schema") == "nico.reader_references.v1",
        approval_receipt_json=json.dumps(edition["review"], sort_keys=True) if receipt_bound else "", repair_current_truth=bool(
        source.get("json", {}).get("human_report_export_schema")))
    canonical = report_package_from_record(record).get('json', {})
    if canonical.get('report_truth_schema') == 'nico.report_truth.v2':
        from nico.comprehensive_certificate_pagination import project_current_phase_pdf
        corrected = project_current_phase_pdf(corrected, canonical, authorized=False)
    certificate, _ = _cover(edition["review"], spanish=record["identity"]["report_language"] == "es-MX",
                            corrected_presentation=True)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(certificate)))
    writer.append(PdfReader(io.BytesIO(corrected)))
    if report_package_from_record(record).get('json', {}).get('report_truth_schema') == 'nico.report_truth.v2':
        from nico.comprehensive_certificate_pagination import annotate_composed_pagination
        annotate_composed_pagination(writer, spanish=record['identity']['report_language'] == 'es-MX')
    writer.add_metadata({"/Title": "NICO Comprehensive — Operator Approved Final", "/Author": "NICO",
                         "/NICOApprovalBasis": "operator_report", "/NICOSourcePDFSHA256": source_hash,
                         "/NICOApprovalCertificateSHA256": edition["review"]["approval_certificate_sha256"],
                         "/NICORenderingVersion": version})
    output = io.BytesIO()
    writer.write(output)
    result = deepcopy(dict(edition))
    result["artifact_schema"] = version
    result["reports"]["pdf_base64"] = base64.b64encode(output.getvalue()).decode()
    result["reports"]["pdf_sha256"] = hashlib.sha256(output.getvalue()).hexdigest()
    if receipt_bound:
        from nico.comprehensive_operator_report_formats import project_operator_report_formats
        project_operator_report_formats(result["reports"], approval_receipt=edition["review"])
    result["artifact_digests"] = _artifact_digests(result["reports"])
    result["report_artifact_digest"] = canonical_sha256(result["artifact_digests"])
    result["rendering_derivation"] = {
        "version": version, "kind": "lifecycle_presentation_correction",
        "new_human_approval": False, "client_delivery_allowed": False,
        "authoritative_approval_manifest_sha256": edition["accepted_edition_manifest_sha256"],
        "original_approved_pdf_sha256": edition["artifact_digests"]["pdf"]["sha256"],
        "approval_certificate_sha256": edition["review"]["approval_certificate_sha256"],
        "reviewed_source_pdf_sha256": source_hash,
        "lifecycle_text_changes": [{"source_page": p, "before": old, "after": new} for p, old, new in changes],
    }
    result.pop("accepted_edition_manifest_sha256", None)
    result["accepted_edition_manifest_sha256"] = canonical_sha256(result)
    return result
