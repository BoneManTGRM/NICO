from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

VERSION = "nico.client-readiness-exact-artifact-approval.v1"

REQUIRED_ARTIFACTS = (
    "markdown",
    "html",
    "pdf",
    "json",
    "findings_csv",
    "evidence_csv",
    "candidate_register_json",
    "remediation_backlog_json",
    "evidence_manifest",
)

REQUIRED_GATES = {
    "candidate_triage": "register_digest",
    "operational_proof": "proof_manifest_sha256",
    "finding_disposition": "register_digest",
    "client_evidence": "register_digest",
    "cross_format_parity": "parity_digest",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_digest(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", _text(value)))


def _valid_sha(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", _text(value)))


def _identity_errors(identity: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("repository", "commit_sha", "run_id", "evidence_ledger_id"):
        if not _text(identity.get(field)):
            errors.append(f"identity.{field} is required")
    if _text(identity.get("commit_sha")) and not _valid_sha(identity.get("commit_sha")):
        errors.append("identity.commit_sha must be a 40-character Git SHA")
    return errors


def _artifact_manifest(
    artifacts: Any,
    report_artifact_digests: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    if isinstance(artifacts, Mapping):
        iterable = []
        for logical_name, value in artifacts.items():
            if isinstance(value, Mapping):
                iterable.append({"logical_name": logical_name, **dict(value)})
            else:
                iterable.append({"logical_name": logical_name})
    elif isinstance(artifacts, list):
        iterable = [dict(item) for item in artifacts if isinstance(item, Mapping)]
    else:
        iterable = []
        errors.append("artifact_manifest must be a mapping or list")

    for index, record in enumerate(iterable):
        logical_name = _text(record.get("logical_name"))
        if not logical_name:
            errors.append(f"artifact_manifest[{index}].logical_name is required")
            continue
        if logical_name in records:
            errors.append(f"duplicate artifact logical_name: {logical_name}")
            continue
        filename = _text(record.get("filename"))
        digest = _text(record.get("sha256")).lower()
        try:
            size_bytes = int(record.get("size_bytes") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        if not filename:
            errors.append(f"artifact {logical_name} is missing filename")
        if not _valid_digest(digest):
            errors.append(f"artifact {logical_name} is missing a valid SHA-256 digest")
        if size_bytes <= 0:
            errors.append(f"artifact {logical_name} is missing a positive size_bytes")
        records[logical_name] = {
            "logical_name": logical_name,
            "filename": filename,
            "sha256": digest,
            "size_bytes": size_bytes,
        }

    missing = sorted(set(REQUIRED_ARTIFACTS).difference(records))
    if missing:
        errors.append("missing required artifacts: " + ",".join(missing))
    unexpected = sorted(set(records).difference(REQUIRED_ARTIFACTS))
    if unexpected:
        errors.append("unexpected approval artifacts: " + ",".join(unexpected))

    for name in ("markdown", "html", "pdf", "json"):
        expected = report_artifact_digests.get(name)
        expected_digest = _text(expected.get("sha256")) if isinstance(expected, Mapping) else ""
        expected_size = int(expected.get("size_bytes") or 0) if isinstance(expected, Mapping) else 0
        record = records.get(name) or {}
        if expected_digest and _text(record.get("sha256")) != expected_digest:
            errors.append(f"artifact {name} does not match the generated report digest")
        if expected_size and int(record.get("size_bytes") or 0) != expected_size:
            errors.append(f"artifact {name} does not match the generated report size")
    return records, errors


def _gate_errors(
    gates: Any,
    identity: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    source = gates if isinstance(gates, Mapping) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for gate_name, digest_field in REQUIRED_GATES.items():
        gate = source.get(gate_name) if isinstance(source.get(gate_name), Mapping) else {}
        digest = _text(gate.get(digest_field)).lower()
        if _text(gate.get("status")).lower() != "passed":
            errors.append(f"{gate_name} gate has not passed")
        if not _valid_digest(digest):
            errors.append(f"{gate_name}.{digest_field} is missing or invalid")
        for field in ("repository", "commit_sha", "run_id"):
            supplied = _text(gate.get(field))
            expected = _text(identity.get(field))
            if supplied and supplied != expected:
                errors.append(f"{gate_name} identity mismatch: {field}")
        if gate.get("client_delivery_allowed") is True:
            errors.append(f"{gate_name} improperly attempts to authorize client delivery")
        normalized[gate_name] = {
            "status": _text(gate.get("status")).lower(),
            digest_field: digest,
        }
    unexpected = sorted(set(source).difference(REQUIRED_GATES))
    if unexpected:
        errors.append("unexpected readiness gates: " + ",".join(unexpected))
    return normalized, errors


def _authority_errors(value: Any, prefix: str) -> list[str]:
    record = value if isinstance(value, Mapping) else {}
    errors: list[str] = []
    for field in ("identity", "role", "authorization_basis", "recorded_at"):
        if not _text(record.get(field)):
            errors.append(f"{prefix}.{field} is required")
    if record.get("authorized") is not True:
        errors.append(f"{prefix}.authorized must be true")
    return errors


def build_approval_subject(
    *,
    identity: Mapping[str, Any],
    report_artifact_digests: Mapping[str, Any],
    artifact_manifest: Any,
    readiness_gates: Any,
) -> dict[str, Any]:
    normalized_identity = {
        "repository": _text(identity.get("repository")),
        "commit_sha": _text(identity.get("commit_sha")).lower(),
        "run_id": _text(identity.get("run_id")),
        "evidence_ledger_id": _text(identity.get("evidence_ledger_id")),
    }
    errors = _identity_errors(normalized_identity)
    artifacts, artifact_errors = _artifact_manifest(artifact_manifest, report_artifact_digests)
    gates, gate_errors = _gate_errors(readiness_gates, normalized_identity)
    errors.extend(artifact_errors)
    errors.extend(gate_errors)
    subject_basis = {
        "schema_version": VERSION,
        "identity": normalized_identity,
        "artifacts": {name: artifacts[name] for name in sorted(artifacts)},
        "readiness_gates": {name: gates[name] for name in sorted(gates)},
    }
    subject_digest = _sha256(subject_basis)
    return {
        **subject_basis,
        "status": "ready_for_human_approval" if not errors else "blocked",
        "validation_errors": sorted(set(errors)),
        "approval_subject_sha256": subject_digest,
        "client_delivery_allowed": False,
        "automation_may_approve": False,
        "rule": "This immutable subject may be approved only by an authorized human. Any artifact, evidence, gate, score, finding, or disposition change creates a different subject digest.",
    }


def evaluate_exact_artifact_approval(
    subject: Mapping[str, Any],
    receipt: Any,
) -> dict[str, Any]:
    errors = [str(item) for item in subject.get("validation_errors") or []]
    if subject.get("status") != "ready_for_human_approval":
        errors.append("approval subject is not ready for human approval")
    approval = deepcopy(dict(receipt)) if isinstance(receipt, Mapping) else {}
    errors.extend(_authority_errors(approval.get("reviewer"), "reviewer"))
    decision = _text(approval.get("decision")).lower()
    if decision != "approved":
        errors.append("human approval decision must be approved")
    if not _text(approval.get("decision_reason")):
        errors.append("decision_reason is required")
    approved_subject = _text(approval.get("approved_subject_sha256")).lower()
    if approved_subject != _text(subject.get("approval_subject_sha256")).lower():
        errors.append("approved_subject_sha256 does not match the exact current subject")

    risk = approval.get("residual_risk_acceptance") if isinstance(approval.get("residual_risk_acceptance"), Mapping) else {}
    errors.extend(_authority_errors(risk, "residual_risk_acceptance"))
    if not _text(risk.get("scope")):
        errors.append("residual_risk_acceptance.scope is required")
    if not _text(risk.get("statement")):
        errors.append("residual_risk_acceptance.statement is required")

    approved = not errors
    receipt_basis = {
        "schema_version": VERSION,
        "approval_subject_sha256": _text(subject.get("approval_subject_sha256")),
        "reviewer": approval.get("reviewer") if isinstance(approval.get("reviewer"), Mapping) else {},
        "decision": decision,
        "decision_reason": _text(approval.get("decision_reason")),
        "residual_risk_acceptance": risk,
    }
    receipt_digest = _sha256(receipt_basis)
    return {
        "schema_version": VERSION,
        "status": "approved" if approved else "blocked",
        "approval_subject": deepcopy(dict(subject)),
        "approval_subject_sha256": subject.get("approval_subject_sha256") or "",
        "approval_receipt": receipt_basis,
        "approval_receipt_sha256": receipt_digest,
        "validation_errors": sorted(set(errors)),
        "human_approval_valid": approved,
        "client_delivery_allowed": approved,
        "approved_final": approved,
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rule": "Client delivery authorization is derived from a valid authorized-human receipt for this exact immutable subject; it is never a caller-controlled flag.",
    }


def validate_exact_artifact_approval(approval: Any) -> dict[str, Any]:
    if not isinstance(approval, Mapping):
        return {"status": "blocked", "validation_errors": ["client readiness approval is required"]}
    errors = [str(item) for item in approval.get("validation_errors") or []]
    subject = approval.get("approval_subject") if isinstance(approval.get("approval_subject"), Mapping) else {}
    receipt = approval.get("approval_receipt") if isinstance(approval.get("approval_receipt"), Mapping) else {}
    claimed_subject = _text(approval.get("approval_subject_sha256"))
    subject_payload = {
        key: subject.get(key)
        for key in ("schema_version", "identity", "artifacts", "readiness_gates")
    }
    if claimed_subject != _sha256(subject_payload):
        errors.append("approval subject digest is invalid")
    claimed_receipt = _text(approval.get("approval_receipt_sha256"))
    if claimed_receipt != _sha256(receipt):
        errors.append("approval receipt digest is invalid")
    if _text(receipt.get("approval_subject_sha256")) != claimed_subject:
        errors.append("approval receipt is not bound to the exact subject")
    if approval.get("human_approval_valid") is not True:
        errors.append("authorized human approval is not valid")
    if approval.get("client_delivery_allowed") is not True:
        errors.append("client delivery is not authorized by the exact approval")
    if approval.get("approved_final") is not True:
        errors.append("exact artifact package is not approved final")
    return {
        "status": "approved" if not errors else "blocked",
        "validation_errors": sorted(set(errors)),
        "approval_subject_sha256": claimed_subject,
        "approval_receipt_sha256": claimed_receipt,
        "client_delivery_allowed": not errors,
    }


__all__ = [
    "REQUIRED_ARTIFACTS",
    "REQUIRED_GATES",
    "VERSION",
    "build_approval_subject",
    "evaluate_exact_artifact_approval",
    "validate_exact_artifact_approval",
]
