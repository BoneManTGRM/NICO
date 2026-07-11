from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from nico.full_assessment_delivery import APPROVED_DELIVERY_STYLE_VERSION

FINAL_REVIEW_ACTION = "final_report_approval"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decode_pdf(value: Any) -> bytes:
    encoded = str(value or "").strip()
    if not encoded:
        return b""
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception:
        return b""
    return decoded if decoded.startswith(b"%PDF") else b""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _sha256(canonical)


def _check(check_id: str, passed: bool, message: str) -> dict[str, Any]:
    return {"id": check_id, "passed": bool(passed), "message": message}


def approved_delivery_metadata(artifact: Any, *, include_pdf: bool = False) -> dict[str, Any]:
    value = _dict(artifact)
    if not value:
        return {}
    metadata = {
        "status": value.get("status") or "unavailable",
        "artifact_type": value.get("artifact_type") or "",
        "style_version": value.get("style_version") or "",
        "run_id": value.get("run_id") or "",
        "report_id": value.get("report_id") or "",
        "approval_id": value.get("approval_id") or "",
        "approver": value.get("approver") or "",
        "approved_at": value.get("approved_at") or "",
        "client_delivery_allowed": bool(value.get("client_delivery_allowed")),
        "human_review_completed": bool(value.get("human_review_completed")),
        "pdf_filename": value.get("pdf_filename") or "",
        "pdf_sha256": value.get("pdf_sha256") or "",
        "source_draft_pdf_sha256": value.get("source_draft_pdf_sha256") or "",
        "approval_identity_sha256": value.get("approval_identity_sha256") or "",
        "disclosure": value.get("disclosure") or "",
    }
    if include_pdf:
        metadata["pdf_base64"] = value.get("pdf_base64") or ""
    return metadata


def verify_approved_delivery_artifact(report: Any, approval: Any) -> dict[str, Any]:
    """Recompute every identity and content hash required for approved delivery."""

    report_value = _dict(report)
    approval_value = _dict(approval)
    artifact = _dict(report_value.get("approved_delivery"))
    formats = _dict(report_value.get("formats"))
    assessment = _dict(formats.get("json"))
    decision = _dict(approval_value.get("review_decision"))
    identity = _dict(artifact.get("identity"))

    source_pdf = _decode_pdf(formats.get("pdf"))
    approved_pdf = _decode_pdf(artifact.get("pdf_base64"))
    source_hash = _sha256(source_pdf) if source_pdf else ""
    approved_hash = _sha256(approved_pdf) if approved_pdf else ""

    run_id = str(report_value.get("run_id") or "")
    report_id = str(report_value.get("report_id") or "")
    approval_id = str(approval_value.get("approval_id") or "")
    approver = str(approval_value.get("approver") or decision.get("actor") or "").strip()
    approved_at = str(artifact.get("approved_at") or "")
    expected_identity = {
        "approval_id": approval_id,
        "approved_at": approved_at,
        "approver": approver,
        "report_id": report_id,
        "run_id": run_id,
        "source_draft_pdf_sha256": source_hash,
        "style_version": APPROVED_DELIVERY_STYLE_VERSION,
    }
    expected_identity_hash = _identity_hash(expected_identity) if all(expected_identity.values()) else ""

    checks = [
        _check("report_exists", bool(report_value) and report_value.get("status") != "not_found", "The stored report package exists."),
        _check("artifact_exists", bool(artifact), "A separate approved-delivery artifact exists."),
        _check("full_assessment_identity", str(assessment.get("report_path") or "") == "full_run", "The source report identifies itself as a Full Assessment."),
        _check("approval_exists", bool(approval_value), "The bound approval record exists."),
        _check("approval_action", str(approval_value.get("requested_action") or "") == FINAL_REVIEW_ACTION, "The approval record is a final report approval."),
        _check("approval_state", str(approval_value.get("status") or "") == "approved", "The human-review decision is approved."),
        _check("human_reviewer", bool(approver), "A human reviewer identity is recorded."),
        _check("run_id_binding", bool(run_id) and str(artifact.get("run_id") or "") == run_id and str(approval_value.get("run_id") or "") == run_id, "Report, approval, and artifact share the exact run ID."),
        _check("report_id_binding", bool(report_id) and str(artifact.get("report_id") or "") == report_id and str(approval_value.get("report_id") or "") == report_id, "Report, approval, and artifact share the exact report ID."),
        _check("approval_id_binding", bool(approval_id) and str(artifact.get("approval_id") or "") == approval_id, "The artifact is bound to the exact approval ID."),
        _check("scope_binding", str(report_value.get("customer_id") or "") == str(approval_value.get("customer_id") or "") and str(report_value.get("project_id") or "") == str(approval_value.get("project_id") or ""), "Report and approval share the same customer and project scope."),
        _check("approved_at_binding", bool(approved_at) and str(decision.get("decided_at") or "") == approved_at, "The artifact approval time matches the immutable review decision."),
        _check("style_version", str(artifact.get("style_version") or "") == APPROVED_DELIVERY_STYLE_VERSION, "The artifact uses the supported approved-delivery style version."),
        _check("source_pdf_integrity", bool(source_pdf), "The preserved source draft is a valid PDF."),
        _check("approved_pdf_integrity", bool(approved_pdf), "The approved delivery artifact is a valid PDF."),
        _check("source_pdf_hash", bool(source_hash) and str(artifact.get("source_draft_pdf_sha256") or "") == source_hash, "The preserved source draft SHA-256 matches the artifact record."),
        _check("approved_pdf_hash", bool(approved_hash) and str(artifact.get("pdf_sha256") or "") == approved_hash, "The approved PDF SHA-256 matches the stored bytes."),
        _check("identity_payload", bool(identity) and identity == expected_identity, "The stored approval identity payload matches the report, approval, reviewer, time, style, and source hash."),
        _check("identity_hash", bool(expected_identity_hash) and str(artifact.get("approval_identity_sha256") or "") == expected_identity_hash, "The approval identity SHA-256 matches the recomputed canonical identity."),
        _check("delivery_flag", artifact.get("client_delivery_allowed") is True and artifact.get("human_review_completed") is True, "The artifact records completed human review and approved client delivery."),
    ]
    blockers = [item["message"] for item in checks if not item["passed"]]
    verified = not blockers
    return {
        "status": "verified" if verified else "blocked",
        "verified": verified,
        "run_id": run_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "checks": checks,
        "blockers": blockers,
        "computed": {
            "pdf_sha256": approved_hash,
            "source_draft_pdf_sha256": source_hash,
            "approval_identity_sha256": expected_identity_hash,
        },
        "rule": "Client delivery is allowed only when the stored report, approval, source draft, approved PDF, scope, and all three SHA-256 bindings verify together.",
    }
