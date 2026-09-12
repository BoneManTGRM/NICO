"""Explicit client-release permission for a retained operator-approved report.

Permission is not transmission or specialist completion. The original approval,
source artifacts and review ledger remain immutable, with a separate receipt.
"""
from __future__ import annotations

import base64
import io
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_operator_approval_v1 import (
    _artifact_digests, _cover, presented_operator_identity, validated_operator_edition,
)
from nico.comprehensive_operator_presentation_v1 import _render_source, render_operator_presentation
from nico.comprehensive_review_decision_v1 import report_package_from_record
from nico.comprehensive_run_record import _record_hash

VERSION = "nico.operator_client_delivery.v1"


def validated_operator_delivery(record: Mapping[str, Any]) -> dict[str, Any] | None:
    edition = record.get("operator_delivery_edition")
    if not isinstance(edition, Mapping):
        return None
    try:
        approved = validated_operator_edition(record)
        if not approved:
            return None
        candidate = dict(edition)
        claimed = candidate.pop("accepted_edition_manifest_sha256")
        if claimed != canonical_sha256(candidate) or edition["artifact_schema"] != VERSION:
            return None
        receipt = dict(edition["delivery_authorization"])
        certificate = receipt.pop("delivery_authorization_certificate_sha256")
        if certificate != canonical_sha256(receipt):
            return None
        if receipt["authorization_basis"] != "authenticated_operator_and_explicit_exact_edition_acknowledgement":
            return None
        if any(not str(receipt[key]).strip() for key in ("authorized_at", "authorizer", "authorizer_role", "reason")):
            return None
        if receipt["artifact_schema"] != VERSION or receipt["client_delivery_allowed"] is not True:
            return None
        if receipt["transmission_performed"] is not False or receipt["specialist_work_completed_by_this_authorization"] is not False:
            return None
        if receipt["approval_certificate_sha256"] != approved["review"]["approval_certificate_sha256"]:
            return None
        if receipt["original_approval_manifest_sha256"] != approved["accepted_edition_manifest_sha256"]:
            return None
        expected = deepcopy(receipt["authorized_artifact_identity"])
        if int(expected["revision"]) >= int(record["revision"]):
            return None
        expected["revision"] = record["revision"]
        if expected != presented_operator_identity(record, approved):
            return None
        if edition["review"] != approved["review"] or edition["source_review_artifact_identity"] != approved["source_review_artifact_identity"]:
            return None
        digests = _artifact_digests(edition["reports"])
        if digests != edition["artifact_digests"] or canonical_sha256(digests) != edition["report_artifact_digest"]:
            return None
        return deepcopy(dict(edition))
    except (KeyError, TypeError, ValueError):
        return None


def authorize_operator_delivery(service: Any, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("delivery_kind") != "operator_report" or any(payload.get(key) is not True for key in (
        "delivery_authorized", "authorization_confirmed",
    )):
        raise ValueError("explicit_delivery_authorization_required")
    record = service.load_read_only(run_id)
    approved = validated_operator_edition(record)
    if not approved:
        raise ValueError("delivery_authorization_requires_current_operator_approval")
    existing = validated_operator_delivery(record)
    expected = payload.get("expected_artifact_identity")
    # An identical retry returns the already committed receipt; it cannot create
    # a second permission or authorize an edition that was never acknowledged.
    if existing and expected == existing["delivery_authorization"]["authorized_artifact_identity"]:
        return record
    if existing or record.get("operator_delivery_edition"):
        raise ValueError("client_delivery_already_authorized_or_invalidated")
    identity = presented_operator_identity(record, approved)
    if not isinstance(expected, Mapping) or dict(expected) != identity:
        raise ValueError("stale_review_artifact_identity")
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    receipt = {
        "artifact_schema": VERSION, "authorized_at": timestamp,
        "authorizer": str(payload.get("authorizer") or "").strip() or "Authenticated NICO operator",
        "authorizer_role": str(payload.get("authorizer_role") or "").strip() or "Authenticated operator",
        "reason": str(payload.get("authorization_reason") or "").strip() or "Explicit client-delivery authorization including disclosed limitations and outstanding review/QC.",
        "authorization_basis": "authenticated_operator_and_explicit_exact_edition_acknowledgement",
        "authorized_artifact_identity": identity,
        "approval_certificate_sha256": approved["review"]["approval_certificate_sha256"],
        "original_approval_manifest_sha256": approved["accepted_edition_manifest_sha256"],
        "client_delivery_allowed": True, "transmission_performed": False,
        "specialist_work_completed_by_this_authorization": False,
    }
    receipt["delivery_authorization_certificate_sha256"] = canonical_sha256(receipt)
    edition = render_operator_presentation(record, approved)
    source_pdf = base64.b64decode(report_package_from_record(record)["pdf_base64"], validate=True)
    corrected, _changes = _render_source(source_pdf, client_delivery_authorized=True)
    certificate, _text = _cover(approved["review"], spanish=record["identity"]["report_language"] == "es-MX",
                                corrected_presentation=True, delivery_authorization=receipt)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(certificate)))
    writer.append(PdfReader(io.BytesIO(corrected)))
    writer.add_metadata({"/Title": "NICO Comprehensive — Client Delivery Authorized",
                         "/NICOSourcePDFSHA256": approved["source_review_artifact_identity"]["artifact_digests"]["pdf"]["sha256"],
                         "/NICOApprovalCertificateSHA256": receipt["approval_certificate_sha256"],
                         "/NICODeliveryAuthorizationSHA256": receipt["delivery_authorization_certificate_sha256"]})
    output = io.BytesIO()
    writer.write(output)
    edition["artifact_schema"] = VERSION
    edition["delivery_authorization"] = receipt
    edition["reports"]["pdf_base64"] = base64.b64encode(output.getvalue()).decode()
    edition["reports"]["pdf_filename"] = edition["reports"]["pdf_filename"].replace("OPERATOR-APPROVED-FINAL", "CLIENT-DELIVERY-AUTHORIZED")
    edition["artifact_digests"] = _artifact_digests(edition["reports"])
    edition["reports"]["pdf_sha256"] = edition["artifact_digests"]["pdf"]["sha256"]
    edition["report_artifact_digest"] = canonical_sha256(edition["artifact_digests"])
    edition["rendering_derivation"] = {"version": VERSION, "kind": "explicit_client_delivery_authorization",
                                       "authorized_artifact_identity": identity, "new_human_approval": False,
                                       "delivery_authorization_certificate_sha256": receipt["delivery_authorization_certificate_sha256"]}
    edition.pop("accepted_edition_manifest_sha256", None)
    edition["accepted_edition_manifest_sha256"] = canonical_sha256(edition)
    updated = deepcopy(record)
    updated["operator_delivery_edition"] = edition
    updated["client_delivery_allowed"] = True
    updated["revision"] = int(record["revision"]) + 1
    updated["updated_at"] = timestamp
    updated["integrity_sha256"] = _record_hash(updated)
    if not validated_operator_delivery(updated):
        raise ValueError("operator_delivery_artifact_validation_failed")
    return service._store.save(updated, expected_revision=record["revision"])


def operator_delivery_identity(record: Mapping[str, Any], edition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_schema": "nico.comprehensive_review_artifact_identity.v1",
        "run_id": record["identity"]["run_id"], "revision": record["revision"],
        "report_artifact_digest": edition["report_artifact_digest"], "artifact_digests": edition["artifact_digests"],
    }


def project_operator_delivery(response: dict[str, Any], record: Mapping[str, Any], *, include_reports: bool) -> dict[str, Any]:
    if not record.get("operator_delivery_edition"):
        return response
    edition = validated_operator_delivery(record)
    allowed = edition is not None
    response["client_delivery_allowed"] = allowed
    response["delivery_status"] = "authorized" if allowed else "invalidated_source_or_artifact_changed"
    for key in ("record", "acceptance"):
        if isinstance(response.get(key), dict):
            response[key]["client_delivery_allowed"] = allowed
            response[key]["delivery_status"] = response["delivery_status"]
    if edition:
        response["delivery_authorization"] = edition["delivery_authorization"]
        if include_reports:
            response["operator_approved_edition"] = edition
            response["review_artifact_identity"] = operator_delivery_identity(record, edition)
    return response
