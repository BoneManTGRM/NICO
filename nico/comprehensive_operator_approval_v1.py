"""Explicit report approval, independent of specialist completion and delivery.

Source artifacts and specialist ledgers remain unchanged. A separately bound
operator edition supplies the approved PDF; it is never a delivery credential.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from html import escape
from typing import Any

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_review_decision_v1 import (
    assert_expected_review_artifact_identity,
    report_package_from_record,
    review_artifact_identity,
)
from nico.comprehensive_run_record import _record_hash

VERSION = "nico.comprehensive_operator_approval.v1"
BASIS = "operator_report"


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def _digest(value: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(value).hexdigest(), "size_bytes": len(value)}


def _artifact_digests(reports: Mapping[str, Any]) -> dict[str, Any]:
    pdf = base64.b64decode(str(reports["pdf_base64"]), validate=True)
    if not pdf.startswith(b"%PDF"):
        raise ValueError("operator_approved_pdf_invalid")
    return {"pdf": _digest(pdf), "json": _digest(_bytes(reports["json"])),
            "markdown": _digest(str(reports["markdown"]).encode()),
            "html": _digest(str(reports["html"]).encode())}


def review_disclosure(record: Mapping[str, Any]) -> dict[str, Any]:
    """Read canonical obligations; absence is unknown, never fabricated completion."""
    from nico.comprehensive_review_work_runtime_v1 import _review_action_record
    from nico.comprehensive_review_work_safe_v1 import review_work_projection
    try:
        projection = review_work_projection(_review_action_record(dict(record)))
    except ValueError as exc:
        if str(exc) != "review_work_canonical_register_unavailable":
            raise
        return {"status": "not_available", "specialist_review_completed":
                record.get("human_review_completed") is True,
                "independent_qc_completed": None,
                "notice": "Specialist review/QC completion is not established by operator approval."}
    required = int(projection.get("quality_control_required_count") or 0)
    completed = int(projection.get("quality_control_completed_count") or 0)
    return {
        "status": "observed",
        "specialist_review_completed": record.get("human_review_completed") is True,
        "ready_for_specialist_approval": projection.get("ready_for_final_approval") is True,
        "remaining_candidate_count": projection.get("remaining_candidate_count"),
        "quality_control_required_count": required,
        "quality_control_completed_count": completed,
        "independent_qc_completed": completed == required,
        "open_evidence_request_count": projection.get("open_evidence_request_count"),
        "unresolved_high_impact_candidate_ids": projection.get("unresolved_high_impact_candidate_ids") or [],
        "review_work_ledger_sha256": canonical_sha256(projection.get("ledger") or {}),
    }


def _cover(statement: Mapping[str, Any], *, spanish: bool, corrected_presentation: bool = False,
           delivery_authorization: Mapping[str, Any] | None = None) -> tuple[bytes, str]:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    heading = ("NICO Comprehensive — FINAL APROBADO POR EL OPERADOR" if spanish
               else "NICO Comprehensive — OPERATOR APPROVED FINAL")
    explanation = (
        "El operador autenticado aprobó este informe exacto, incluidas sus limitaciones y el trabajo pendiente. "
        "Esta aprobación no certifica que la revisión especializada o el control de calidad independiente estén terminados. "
        "La entrega al cliente sigue BLOQUEADA y requiere autorización separada. "
        "Las páginas siguientes conservan el informe fuente revisado sin cambios. Sus marcadores de borrador o aprobación pendiente describen la edición fuente anterior a este certificado."
        if spanish else
        "The authenticated operator approved this exact report, including its limitations and outstanding work. "
        "This approval does not certify completed specialist review or independent quality control. "
        "Client delivery remains BLOCKED and requires separate authorization. "
        "The following pages preserve the reviewed source report unchanged. Draft or pending-approval markers on those pages describe the source edition before this certificate."
    )
    if corrected_presentation:
        explanation = (
            "El operador autenticado aprobó este informe exacto, incluidas sus limitaciones y el trabajo pendiente. "
            "La revisión especializada y el control de calidad siguen registrados por separado. "
            "La entrega al cliente sigue BLOQUEADA y requiere autorización separada. "
            "Esta presentación corrige únicamente los rótulos de aprobación; conserva los hallazgos, las puntuaciones y la evidencia. "
            "El informe fuente y el archivo aprobado original permanecen conservados con sus identidades verificables."
            if spanish else
            "The authenticated operator approved this exact report, including its limitations and outstanding work. "
            "Specialist review and independent quality control remain recorded separately. "
            "Client delivery remains BLOCKED and requires separate authorization. "
            "This presentation corrects approval labels only; findings, scores, and evidence are preserved. "
            "The reviewed source and original certified export remain retained under their verifiable identities."
        )
    if delivery_authorization:
        explanation = explanation.replace(
            "Client delivery remains BLOCKED and requires separate authorization.",
            "Client delivery is AUTHORIZED by the separate exact-edition permission below. This does not mean the report has been sent.",
        ).replace(
            "La entrega al cliente sigue BLOQUEADA y requiere autorización separada.",
            "La entrega al cliente está AUTORIZADA mediante el permiso separado de esta edición. Esto no significa que se haya enviado el informe.",
        )
    disclosure = statement["review_disclosure"]
    identity = statement["source_identity"]
    source = statement["source_review_artifact_identity"]
    labels = ([("Operador", statement["reviewer"]), ("Función (metadatos)", statement["reviewer_role"]),
               ("Fecha", statement["decided_at"]), ("Ejecución", identity["run_id"]),
               ("Commit", identity["commit_sha"]), ("Idioma", identity["report_language"]),
               ("Revisión fuente", source["revision"]), ("SHA-256 PDF fuente", source["artifact_digests"]["pdf"]["sha256"])]
              if spanish else
              [("Operator", statement["reviewer"]), ("Role (metadata)", statement["reviewer_role"]),
               ("Approved at", statement["decided_at"]), ("Run", identity["run_id"]),
               ("Commit", identity["commit_sha"]), ("Language", identity["report_language"]),
               ("Source revision", source["revision"]), ("Source PDF SHA-256", source["artifact_digests"]["pdf"]["sha256"])])
    if disclosure["status"] == "observed":
        labels.extend([
            ("Revisión de candidatos pendiente" if spanish else "Pending candidate review", disclosure["remaining_candidate_count"]),
            ("Muestras QC completadas / requeridas" if spanish else "QC samples completed / required",
             f'{disclosure["quality_control_completed_count"]} / {disclosure["quality_control_required_count"]}'),
            ("Escalaciones pendientes" if spanish else "Open escalations", len(disclosure["unresolved_high_impact_candidate_ids"])),
            ("Solicitudes de evidencia abiertas" if spanish else "Open evidence requests", disclosure["open_evidence_request_count"]),
        ])
    else:
        labels.append(("Revisión/QC" if spanish else "Specialist review/QC", "No verificado" if spanish else "Not established"))
    labels.append(("Motivo" if spanish else "Approval reason", statement["reason"]))
    if delivery_authorization:
        labels.extend([
            ("Entrega autorizada por" if spanish else "Delivery authorized by", delivery_authorization["authorizer"]),
            ("Fecha de autorización" if spanish else "Delivery authorized at", delivery_authorization["authorized_at"]),
            ("SHA-256 autorización" if spanish else "Delivery authorization SHA-256", delivery_authorization["delivery_authorization_certificate_sha256"]),
        ])
    text = heading + "\n\n" + explanation + "\n\n" + "\n".join(f"{key}: {value}" for key, value in labels)
    styles = getSampleStyleSheet()
    stream = io.BytesIO()
    document = SimpleDocTemplate(stream, pagesize=letter, title=heading, author="NICO", invariant=1)
    story = [Paragraph(escape(heading), styles["Title"]), Spacer(1, 12),
             Paragraph(escape(explanation), styles["BodyText"]), Spacer(1, 12)]
    story.extend(Paragraph(f"<b>{escape(str(key))}:</b> {escape(str(value))}", styles["BodyText"])
                 for key, value in labels)
    document.build(story)
    return stream.getvalue(), text


def build_operator_edition(record: dict[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    from nico.comprehensive_run_service import _require_exact_final_report_integrity
    if any(payload.get(key) is not True for key in (
        "review_authorized", "authorization_confirmed", "exact_report_acknowledged",
    )):
        raise ValueError("explicit_exact_report_operator_approval_required")
    if payload.get("approval_kind") != BASIS or payload.get("decision") != "approved":
        raise ValueError("operator_approval_decision_invalid")
    if record.get("terminal") is not True or record.get("status") != "review_required":
        raise ValueError("operator_approval_completed_assessment_required")
    _require_exact_final_report_integrity(record)
    source_identity = assert_expected_review_artifact_identity(record, payload.get("expected_artifact_identity"))
    if validated_operator_edition(record):
        raise ValueError("operator_approval_already_recorded")
    statement = {
        "artifact_schema": VERSION, "decision": "approved", "approval_basis": BASIS,
        "reviewer": str(payload.get("reviewer") or "").strip() or "Authenticated NICO operator",
        "reviewer_role": str(payload.get("reviewer_role") or "").strip() or "Authenticated operator",
        "reason": str(payload.get("decision_reason") or "").strip() or "Explicit approval of the exact report including disclosed limitations and outstanding work.",
        "decided_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_identity": deepcopy(record["identity"]),
        "source_review_artifact_identity": source_identity,
        "source_review_work_ledger_sha256": canonical_sha256(record.get("review_work_ledger") or {}),
        "review_disclosure": review_disclosure(record),
        "specialist_work_completed_by_this_approval": False,
        "client_delivery_allowed": False,
    }
    source = report_package_from_record(record)
    pdf = base64.b64decode(source["pdf_base64"], validate=True)
    if _digest(pdf) != source_identity["artifact_digests"]["pdf"]:
        raise ValueError("operator_approval_source_pdf_hash_mismatch")
    cover, cover_text = _cover(statement, spanish=record["identity"]["report_language"] == "es-MX")
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(cover)))
    writer.append(PdfReader(io.BytesIO(pdf)))
    writer.add_metadata({"/Title": "NICO Comprehensive — Operator Approved Final", "/Author": "NICO",
                         "/NICOApprovalBasis": BASIS, "/NICOSourcePDFSHA256": _digest(pdf)["sha256"]})
    output = io.BytesIO()
    writer.write(output)
    reports = {
        "pdf_base64": base64.b64encode(output.getvalue()).decode(),
        "pdf_sha256": hashlib.sha256(output.getvalue()).hexdigest(),
        "pdf_filename": f'nico-comprehensive-{record["identity"]["run_id"]}-{record["identity"]["report_language"]}-OPERATOR-APPROVED-FINAL.pdf',
        "markdown": cover_text + "\n\n---\n\n" + str(source.get("markdown") or ""),
        "html": "<section><pre>" + escape(cover_text) + "</pre></section>" + str(source.get("html") or ""),
        "json": {**deepcopy(source["json"]), "operator_approval": deepcopy(statement)},
    }
    digests = _artifact_digests(reports)
    review = {**statement, "approved_artifact_digests": digests}
    review["approval_certificate_sha256"] = canonical_sha256(review)
    edition = {"artifact_schema": VERSION, "review": review, "artifact_digests": digests,
               "report_artifact_digest": canonical_sha256(digests), "reports": reports,
               "source_review_artifact_identity": source_identity}
    edition["accepted_edition_manifest_sha256"] = canonical_sha256(edition)
    return edition


def validated_operator_edition(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """Never project stale/corrupt approval; retain it as historical evidence."""
    edition = record.get("operator_approved_edition")
    if not isinstance(edition, Mapping):
        return None
    try:
        from nico.comprehensive_run_service import _require_exact_final_report_integrity
        if record.get("terminal") is not True or record.get("status") != "review_required":
            return None
        # Validate the retained source independently of the later delivery receipt.
        # The caller validates that receipt separately; source bytes stay a draft.
        _require_exact_final_report_integrity({**record, "client_delivery_allowed": False})
        manifest = dict(edition)
        claimed = manifest.pop("accepted_edition_manifest_sha256")
        if claimed != canonical_sha256(manifest) or edition["artifact_schema"] != VERSION:
            return None
        review = dict(edition["review"])
        certificate = review.pop("approval_certificate_sha256")
        if certificate != canonical_sha256(review) or review["approval_basis"] != BASIS or review["decision"] != "approved":
            return None
        if review["client_delivery_allowed"] is not False or review["specialist_work_completed_by_this_approval"] is not False:
            return None
        if review["source_identity"] != record["identity"]:
            return None
        if review["source_review_work_ledger_sha256"] != canonical_sha256(record.get("review_work_ledger") or {}):
            return None
        current = review_artifact_identity(record)
        expected = dict(review["source_review_artifact_identity"])
        if expected != edition["source_review_artifact_identity"]:
            return None
        if int(expected["revision"]) >= int(current["revision"]):
            return None
        expected["revision"] = current["revision"]
        if expected != current:
            return None
        digests = _artifact_digests(edition["reports"])
        if digests != edition["artifact_digests"] or digests != review["approved_artifact_digests"]:
            return None
        if canonical_sha256(digests) != edition["report_artifact_digest"]:
            return None
        return deepcopy(dict(edition))
    except (KeyError, ValueError, TypeError):
        return None


def approve_operator_report(service: Any, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    record = service.load_read_only(run_id)
    edition = build_operator_edition(record, payload)
    previous = int(record["revision"])
    updated = deepcopy(record)
    if updated.get("operator_approved_edition"):
        updated.setdefault("operator_approval_history", []).append(updated["operator_approved_edition"])
    updated["operator_approved_edition"] = edition
    updated["revision"] = previous + 1
    updated["updated_at"] = edition["review"]["decided_at"]
    updated["integrity_sha256"] = _record_hash(updated)
    return service._store.save(updated, expected_revision=previous)


def project_operator_approval(response: dict[str, Any], record: dict[str, Any], *, include_reports: bool) -> dict[str, Any]:
    edition = validated_operator_edition(record)
    if not edition:
        if record.get("operator_approved_edition"):
            response["operator_approval_status"] = "invalidated_source_or_artifact_changed"
        if record.get("operator_delivery_edition"):
            from nico.comprehensive_operator_delivery_v1 import project_operator_delivery
            return project_operator_delivery(response, record, include_reports=include_reports)
        return response
    response["operator_approval_status"] = "approved"
    response["approval_basis"] = BASIS
    response["specialist_approval_status"] = response.get("approval_status")
    response["approval_status"] = "operator_approved_final"
    if include_reports:
        from nico.comprehensive_operator_presentation_v1 import render_operator_presentation
        edition = render_operator_presentation(record, edition)
        response["operator_approved_edition"] = edition
        response["review_artifact_identity"] = presented_operator_identity(record, edition)
    else:
        response["operator_approval"] = edition["review"]
    from nico.comprehensive_operator_delivery_v1 import project_operator_delivery
    return project_operator_delivery(response, record, include_reports=include_reports)


def presented_operator_identity(record: Mapping[str, Any], edition: Mapping[str, Any]) -> dict[str, Any]:
    from nico.comprehensive_operator_presentation_v1 import render_operator_presentation
    edition = render_operator_presentation(record, edition)
    return {
        "artifact_schema": "nico.comprehensive_review_artifact_identity.v1",
        "run_id": record["identity"]["run_id"], "revision": record["revision"],
        "report_artifact_digest": edition["report_artifact_digest"],
        "artifact_digests": edition["artifact_digests"],
    }
