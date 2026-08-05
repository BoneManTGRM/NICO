from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from nico.client_readiness_exact_artifact_approval import (
    build_approval_subject,
    evaluate_exact_artifact_approval,
)
from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition

VERSION = "nico.comprehensive_review_decision.v2"
_REPORT_STAGE_IDS = (
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def report_package_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    stage_results = record.get("stage_results")
    if isinstance(stage_results, Mapping):
        for stage_id in _REPORT_STAGE_IDS:
            stage = stage_results.get(stage_id)
            if not isinstance(stage, Mapping):
                continue
            candidate = stage.get("report_package")
            if isinstance(candidate, Mapping):
                return deepcopy(dict(candidate))
            candidate = stage.get("reports")
            if isinstance(candidate, Mapping):
                return deepcopy(dict(candidate))
    candidate = record.get("reports")
    return deepcopy(dict(candidate)) if isinstance(candidate, Mapping) else {}


def _tree_sha(record: Mapping[str, Any]) -> str:
    stages = record.get("stage_results")
    if not isinstance(stages, Mapping):
        return ""
    stage = stages.get("immutable_repository_snapshot")
    if not isinstance(stage, Mapping):
        return ""
    snapshot = stage.get("snapshot")
    if isinstance(snapshot, Mapping) and snapshot.get("tree_sha"):
        return str(snapshot["tree_sha"]).strip()
    evidence = stage.get("evidence")
    if isinstance(evidence, Mapping) and evidence.get("tree_sha"):
        return str(evidence["tree_sha"]).strip()
    return str(stage.get("tree_sha") or "").strip()


def _scanner_run_id(record: Mapping[str, Any]) -> str:
    stages = record.get("stage_results")
    if not isinstance(stages, Mapping):
        return ""
    for stage_id in ("deep_scanner_triage", "dependency_security_static_analysis"):
        stage = stages.get(stage_id)
        if not isinstance(stage, Mapping):
            continue
        direct = str(stage.get("scan_id") or stage.get("scanner_run_id") or "").strip()
        if direct:
            return direct
        scanner = stage.get("scanner")
        if isinstance(scanner, Mapping):
            nested = str(scanner.get("scan_id") or scanner.get("scanner_run_id") or "").strip()
            if nested:
                return nested
    return ""


def _evidence_bundle_hash(record: Mapping[str, Any], package: Mapping[str, Any]) -> str:
    candidates: list[Any] = [
        package.get("evidence_bundle_sha256"),
        package.get("canonical_truth_sha256"),
    ]
    canonical = package.get("json")
    if isinstance(canonical, Mapping):
        candidates.extend(
            [
                canonical.get("evidence_bundle_sha256"),
                canonical.get("canonical_truth_sha256"),
            ]
        )
    identity = record.get("identity")
    if isinstance(identity, Mapping):
        candidates.append(identity.get("evidence_bundle_hash"))
    for value in candidates:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _bind_client_readiness_approval(
    manifest: dict[str, Any],
    record: Mapping[str, Any],
    *,
    reviewer: str,
    reviewer_role: str,
    reviewer_authorization_basis: str,
    decision_reason: str,
    decided_at: str | None,
    client_readiness: Any,
    residual_risk_acceptance: Any,
) -> dict[str, Any]:
    readiness = client_readiness if isinstance(client_readiness, Mapping) else {}
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    subject = build_approval_subject(
        identity={
            "repository": identity.get("repository"),
            "commit_sha": identity.get("commit_sha"),
            "run_id": identity.get("run_id"),
            "evidence_ledger_id": identity.get("evidence_ledger_id"),
        },
        report_artifact_digests=(
            manifest.get("artifact_digests")
            if isinstance(manifest.get("artifact_digests"), Mapping)
            else {}
        ),
        artifact_manifest=readiness.get("artifact_manifest"),
        readiness_gates=readiness.get("gates"),
    )
    timestamp = str(
        decided_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ).strip()
    approval = evaluate_exact_artifact_approval(
        subject,
        {
            "reviewer": {
                "identity": reviewer,
                "role": reviewer_role,
                "authorized": readiness.get("review_authorized") is True,
                "authorization_basis": reviewer_authorization_basis,
                "recorded_at": timestamp,
            },
            "decision": "approved",
            "decision_reason": decision_reason,
            "approved_subject_sha256": readiness.get("approved_subject_sha256"),
            "residual_risk_acceptance": residual_risk_acceptance,
        },
    )
    manifest["client_readiness_approval"] = approval
    if approval.get("status") != "approved":
        errors = [
            "client_readiness:" + str(item)
            for item in approval.get("validation_errors") or []
        ]
        manifest["validation_errors"] = sorted(
            set(list(manifest.get("validation_errors") or []) + errors)
        )
        manifest["accepted_edition"] = False
        manifest["delivery_status"] = "blocked"
        manifest["client_delivery_allowed"] = False
    manifest_payload = deepcopy(manifest)
    manifest_payload.pop("accepted_edition_manifest_sha256", None)
    manifest["accepted_edition_manifest_sha256"] = _canonical_hash(manifest_payload)
    return manifest


def build_reviewed_edition(
    record: Mapping[str, Any],
    *,
    reviewer: str,
    reviewer_role: str,
    decision: str,
    decision_reason: str,
    decided_at: str | None = None,
    reviewer_authorization_basis: str = "",
    client_readiness: Any = None,
    residual_risk_acceptance: Any = None,
) -> dict[str, Any]:
    """Bind a human decision to the exact already-generated report artifacts.

    Approval is additionally bound to the exact client-readiness artifact manifest,
    all prerequisite gate digests, explicit reviewer authority, and authorized
    residual-risk acceptance. Nonapproval decisions remain delivery-blocked and do
    not require an approval receipt.
    """

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    package = report_package_from_record(record)
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
    except Exception:
        pdf = b""
    manifest = build_accepted_report_edition(
        repository=str(identity.get("repository") or ""),
        commit_sha=str(identity.get("commit_sha") or ""),
        tree_sha=_tree_sha(record),
        run_id=str(identity.get("run_id") or ""),
        scanner_run_id=_scanner_run_id(record),
        evidence_bundle_hash=_evidence_bundle_hash(record, package),
        report_language=str(identity.get("report_language") or ""),
        assessment_depth=str(identity.get("assessment_depth") or ""),
        artifacts={
            "markdown": package.get("markdown"),
            "html": package.get("html"),
            "pdf": pdf,
            "json": package.get("json"),
        },
        reviewer=reviewer,
        reviewer_role=reviewer_role,
        decision=decision,
        decision_reason=decision_reason,
        decided_at=decided_at,
    )
    if str(decision or "").strip().casefold() == "approved":
        manifest = _bind_client_readiness_approval(
            manifest,
            record,
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            reviewer_authorization_basis=reviewer_authorization_basis,
            decision_reason=decision_reason,
            decided_at=decided_at,
            client_readiness=client_readiness,
            residual_risk_acceptance=residual_risk_acceptance,
        )
    return manifest


__all__ = ["VERSION", "build_reviewed_edition", "report_package_from_record"]
