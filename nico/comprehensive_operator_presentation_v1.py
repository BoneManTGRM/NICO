"""Deterministic lifecycle-only view of a retained, valid operator approval.

The stored approval and original certified bytes are never replaced. The rendered
manifest binds the corrected export to that receipt and to the reviewed source.
Rendering is read-only: it creates neither a human decision nor delivery authority.
"""
from __future__ import annotations

import base64
import hashlib
import io
import re
from copy import deepcopy
from functools import lru_cache
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_review_decision_v1 import report_package_from_record

VERSION = "nico.operator_approved_presentation.v1"


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


@lru_cache(maxsize=4)
def _render_source(pdf: bytes) -> tuple[bytes, tuple[tuple[int, str, str], ...]]:
    writer = PdfWriter(clone_from=io.BytesIO(pdf))
    changes: list[tuple[int, str, str]] = []
    for page_index, page in enumerate(writer.pages):
        text = page.extract_text() or ""
        cover = page_index == 0 and ("Executive posture" in text or "Postura ejecutiva" in text)
        approval_record = ("Human Review and Exact-Artifact Approval" in text and "Reviewer identity" in text
                           or "Identidad del revisor" in text and "Registro de aprobación requerido" in text)
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
                normalized = original.strip()
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
    if edition.get("rendering_derivation", {}).get("version") == VERSION:
        return dict(edition)
    from nico.comprehensive_operator_approval_v1 import _artifact_digests, _cover

    source = report_package_from_record(record)
    source_pdf = base64.b64decode(source["pdf_base64"], validate=True)
    source_hash = hashlib.sha256(source_pdf).hexdigest()
    if source_hash != edition["source_review_artifact_identity"]["artifact_digests"]["pdf"]["sha256"]:
        raise ValueError("operator_presentation_source_mismatch")
    corrected, changes = _render_source(source_pdf)
    certificate, _ = _cover(edition["review"], spanish=record["identity"]["report_language"] == "es-MX",
                            corrected_presentation=True)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(certificate)))
    writer.append(PdfReader(io.BytesIO(corrected)))
    writer.add_metadata({"/Title": "NICO Comprehensive — Operator Approved Final", "/Author": "NICO",
                         "/NICOApprovalBasis": "operator_report", "/NICOSourcePDFSHA256": source_hash,
                         "/NICOApprovalCertificateSHA256": edition["review"]["approval_certificate_sha256"],
                         "/NICORenderingVersion": VERSION})
    output = io.BytesIO()
    writer.write(output)
    result = deepcopy(dict(edition))
    result["artifact_schema"] = VERSION
    result["reports"]["pdf_base64"] = base64.b64encode(output.getvalue()).decode()
    result["reports"]["pdf_sha256"] = hashlib.sha256(output.getvalue()).hexdigest()
    result["artifact_digests"] = _artifact_digests(result["reports"])
    result["report_artifact_digest"] = canonical_sha256(result["artifact_digests"])
    result["rendering_derivation"] = {
        "version": VERSION, "kind": "lifecycle_presentation_correction",
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
