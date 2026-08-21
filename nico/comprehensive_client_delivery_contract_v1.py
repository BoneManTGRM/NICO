from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

VERSION = "nico.comprehensive_client_delivery_contract.v1"
PRODUCT_NAME = "NICO Comprehensive"
REPORT_KIND = "nico_comprehensive"
CLIENT_FINAL_CLASSIFICATION = "client_final"
_REQUIRED_ARTIFACTS = ("markdown", "html", "pdf", "json")
_SCOPE_FIELDS = ("customer_id", "client_id", "project_id", "workspace_id", "organization_id", "tenant_id")
_AUTOMATION = {"automation", "automated reviewer", "bot", "nico automation", "system", "system reviewer"}


class ClientDeliveryContractError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code).strip()
        self.detail = str(detail).strip()
        super().__init__(self.code if not self.detail else f"{self.code}:{self.detail}")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _text(value[0]) if value else ""
    return _text(value)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise ClientDeliveryContractError(code, detail)


def _identity(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(record.get("identity"))


def _stages(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(record.get("stage_results"))


def _report(record: Mapping[str, Any]) -> Mapping[str, Any]:
    for stage_id in ("final_comprehensive_report_generation", "risk_reduction_and_executive_briefing", "decision_report_generation", "report_generation", "reports"):
        stage = _mapping(_stages(record).get(stage_id))
        for key in ("report_package", "reports"):
            if isinstance(stage.get(key), Mapping):
                return stage[key]
    return _mapping(record.get("reports"))


def _canonical(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_report(record).get("json"))


def _register(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(_mapping(_canonical(record).get("assessment")).get("canonical_scanner_finding_register"))


def _stakeholder_evidence(record: Mapping[str, Any]) -> Mapping[str, Any]:
    human = _mapping(record.get("human_evidence"))
    modules = _mapping(human.get("modules")) or human
    return _mapping(_mapping(modules.get("stakeholder_context")).get("evidence"))


def engagement_binding(record: Mapping[str, Any]) -> dict[str, Any]:
    identity, evidence = _identity(record), _stakeholder_evidence(record)
    return {
        "mode": _first(evidence.get("engagement_mode")).casefold(),
        "customer_id": _text(identity.get("customer_id") or record.get("customer_id")),
        "client_id": _text(identity.get("client_id") or record.get("client_id")),
        "project_id": _text(identity.get("project_id") or record.get("project_id")),
        "client_identity": _first(evidence.get("client_identity")),
        "project_identity": _first(evidence.get("project_identity")),
        "primary_technical_contact": _first(evidence.get("primary_technical_contact")),
        "access_method": _first(evidence.get("access_method")),
        "authorized_scope": _first(evidence.get("authorized_scope")),
        "repository_identity": _first(evidence.get("repository_identity")),
        "authorization_confirmed": _first(evidence.get("authorization_confirmation")).casefold() == "confirmed",
    }


def version_truth(record: Mapping[str, Any]) -> dict[str, Any]:
    identity, package, canonical, register = _identity(record), _report(record), _canonical(record), _register(record)
    metadata = _mapping(record.get("generator_versions")) or _mapping(canonical.get("generator_versions")) or _mapping(package.get("generator_versions"))
    triage = _mapping(register.get("technical_triage"))
    backend = _text(metadata.get("nico_backend_build_commit") or metadata.get("backend_build_commit") or record.get("nico_build_commit"))
    frontend = _text(metadata.get("frontend_build_commit") or record.get("frontend_build_commit"))
    return {
        "assessed_repository_commit": _text(identity.get("commit_sha")),
        "nico_backend_build_commit": backend or "unavailable",
        "frontend_build_commit": frontend or "unavailable",
        "assessment_engine_version": _text(metadata.get("assessment_engine_version") or record.get("artifact_schema")) or "unavailable",
        "scoring_model_version": _text(metadata.get("scoring_model_version")) or "unavailable",
        "scanner_versions": dict(_mapping(register.get("scanner_versions")) or _mapping(metadata.get("scanner_versions"))),
        "candidate_lineage_version": _text(register.get("candidate_lineage_version") or metadata.get("candidate_lineage_version")) or "unavailable",
        "technical_triage_version": _text(triage.get("version") or metadata.get("technical_triage_version")) or "unavailable",
        "report_renderer_version": _text(metadata.get("report_renderer_version")) or "unavailable",
        "artifact_generation_version": _text(metadata.get("artifact_generation_version") or package.get("artifact_schema")) or "unavailable",
        "mutable_operational_history_reference": _text(record.get("audit_chain_sha256") or record.get("integrity_sha256")) or f"run_revision:{int(record.get('revision') or 0)}",
        "deployment_identity_established": bool(backend and frontend),
    }


def artifact_digests(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    package = _report(record)
    try:
        pdf = base64.b64decode(_text(package.get("pdf_base64")), validate=True)
    except Exception:
        pdf = b""
    values: dict[str, Any] = {"markdown": package.get("markdown"), "html": package.get("html"), "json": package.get("json"), "pdf": pdf}
    for source, name in (("findings_csv", "findings_csv"), ("evidence_csv", "evidence_csv"), ("jira_csv", "remediation_csv"), ("candidate_register_csv", "candidate_register_csv")):
        values[name] = package.get(source)
    output: dict[str, dict[str, Any]] = {}
    for name, value in values.items():
        if value in (None, "", b""):
            continue
        encoded = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else _canonical_bytes(value)
        output[name] = {"sha256": hashlib.sha256(encoded).hexdigest(), "size_bytes": len(encoded)}
    return output


def _identity_scope(record: Mapping[str, Any]) -> dict[str, Any]:
    identity, engagement = _identity(record), engagement_binding(record)
    run_id, repository, commit, ledger_id = (_text(identity.get(key)) for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id"))
    _require(bool(run_id), "missing_assessment_run_id")
    _require(bool(repository), "missing_authorized_repository")
    _require(len(commit) in {40, 64} and all(ch in "0123456789abcdefABCDEF" for ch in commit), "unresolved_assessed_commit")
    _require(bool(ledger_id), "missing_evidence_ledger_id")
    _require(engagement["mode"] == "client", "internal_or_test_package_not_client_final")
    _require(bool(engagement["client_identity"]), "missing_mandatory_client_identity")
    _require(bool(engagement["project_identity"]), "missing_project_identity")
    _require(bool(engagement["customer_id"] and engagement["project_id"]), "missing_client_project_scope_identity")
    _require(engagement["authorization_confirmed"], "assessment_authorization_missing")
    _require(bool(engagement["authorized_scope"]), "authorized_scope_missing")
    access = "".join(engagement["access_method"].casefold().split()).replace("-", "")
    _require("readonly" in access or "readaccess" in access, "repository_access_not_read_only")
    _require(not engagement["repository_identity"] or engagement["repository_identity"].casefold() == repository.casefold(), "repository_outside_approved_scope")
    return {"run_id": run_id, "repository": repository, "commit_sha": commit, "evidence_ledger_id": ledger_id, "engagement": engagement}


def _assert_snapshot(record: Mapping[str, Any], identity: Mapping[str, Any]) -> None:
    snapshot_stage = _mapping(_stages(record).get("immutable_repository_snapshot"))
    snapshot = _mapping(snapshot_stage.get("snapshot")) or snapshot_stage
    commit = _text(snapshot.get("commit_sha") or snapshot.get("resolved_commit_sha") or identity.get("commit_sha"))
    _require(commit == identity["commit_sha"], "report_attached_to_wrong_assessed_commit")
    _require(bool(_text(snapshot.get("tree_sha"))), "immutable_repository_snapshot_missing")


def _scanner_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    contract = _mapping(record.get("scanner_execution_contract"))
    register = _register(record)
    executions = contract.get("executions")
    if not isinstance(executions, list):
        executions = register.get("scanner_executions")
    if not isinstance(executions, list):
        executions = _mapping(_stages(record).get("dependency_security_static_analysis")).get("scanner_executions")
    _require(_text(contract.get("support_status") or "supported").casefold() in {"supported", "applicable"}, "unsupported_ecosystem_not_assessed")
    _require(isinstance(executions, list) and bool(executions), "required_scanner_execution_missing")
    failed: list[str] = []
    unsupported: list[str] = []
    for item in executions:
        if not isinstance(item, Mapping):
            failed.append("malformed")
            continue
        name = _text(item.get("scanner") or item.get("name") or "unknown")
        support = _text(item.get("support_status") or "supported").casefold()
        status = _text(item.get("status")).casefold()
        if support not in {"supported", "applicable"}:
            unsupported.append(name)
        elif status not in {"completed", "passed", "success", "succeeded", "not_applicable"}:
            failed.append(name)
        _require(bool(_text(item.get("artifact_sha256") or item.get("manifest_sha256"))), "scanner_artifact_digest_missing", name)
    _require(not unsupported, "unsupported_ecosystem_not_assessed", ",".join(unsupported))
    _require(not failed, "required_scanner_execution_failed", ",".join(failed))
    return {"scanner_execution_count": len(executions), "scanner_artifacts_retained": True}


def _candidate_contract(record: Mapping[str, Any]) -> dict[str, Any]:
    register = _register(record)
    findings = register.get("findings")
    _require(isinstance(findings, list), "malformed_candidate_register")
    try:
        declared = int(register.get("candidate_record_count"))
    except (TypeError, ValueError):
        declared = -1
    _require(declared == len(findings), "candidate_register_count_mismatch")
    ledger = _mapping(record.get("review_work_ledger"))
    dispositions = _mapping(ledger.get("dispositions"))
    pending_individual: list[str] = []
    triaged = 0
    for row in findings:
        _require(isinstance(row, Mapping), "malformed_candidate_register")
        candidate_id = _text(row.get("candidate_id"))
        _require(bool(candidate_id), "candidate_identity_missing")
        lineage = _mapping(row.get("lineage"))
        _require(bool(_text(row.get("candidate_lineage_version") or lineage.get("version"))) and bool(_text(row.get("lineage_status") or lineage.get("status"))), "stale_candidate_lineage", candidate_id)
        triage = _mapping(row.get("technical_triage"))
        verdict = _text(triage.get("verdict") or row.get("technical_triage_verdict"))
        confidence = triage.get("confidence", row.get("technical_triage_confidence"))
        _require(bool(verdict) and confidence not in (None, ""), "incomplete_required_technical_triage", candidate_id)
        triaged += 1
        has_disposition = candidate_id in dispositions or isinstance(row.get("human_disposition"), Mapping)
        if row.get("review_requires_individual_attention") is True and not has_disposition:
            pending_individual.append(candidate_id)
    _require(not pending_individual, "mandatory_individual_review_unresolved", ",".join(pending_individual))
    return {"total_candidates": len(findings), "technical_triage_completed": triaged, "mandatory_individual_review_pending": len(pending_individual)}


def _review_contract(record: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, Any]:
    ledger = _mapping(record.get("review_work_ledger"))
    _require(bool(ledger), "human_review_ledger_missing")
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        _require(_text(ledger.get(field)) == _text(identity.get(field)), f"cross_run_review_mismatch:{field}")
    scope = _mapping(ledger.get("scope_binding"))
    for field in _SCOPE_FIELDS:
        expected = _text(_identity(record).get(field) or record.get(field))
        if expected:
            _require(_text(scope.get(field)) == expected, f"cross_{field}_review_mismatch")
    _require(int(ledger.get("human_dispositions_pending") or 0) == 0, "human_dispositions_pending")
    source_hash = _text(ledger.get("review_source_sha256"))
    _require(bool(source_hash), "review_source_hash_missing")
    return {"review_work_ledger_sha256": canonical_sha256(ledger), "review_source_sha256": source_hash}


def _artifact_contract(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    package = _report(record)
    _require(_text(package.get("product_name") or package.get("report_product") or PRODUCT_NAME) == PRODUCT_NAME, "alternate_report_product_rejected")
    _require(_text(package.get("report_kind") or REPORT_KIND) == REPORT_KIND, "alternate_report_product_rejected")
    _require(_text(package.get("package_classification") or CLIENT_FINAL_CLASSIFICATION) == CLIENT_FINAL_CLASSIFICATION, "internal_or_test_package_presented_as_client_final")
    _require(package.get("one_client_report", True) is True and int(package.get("client_pdf_count") or 1) == 1, "one_comprehensive_report_required")
    digests = artifact_digests(record)
    for name in _REQUIRED_ARTIFACTS:
        _require(name in digests, "required_final_artifact_missing", name)
    return digests


def operational_metrics(record: Mapping[str, Any]) -> dict[str, Any]:
    register, ledger = _register(record), _mapping(record.get("review_work_ledger"))
    findings = register.get("findings") if isinstance(register.get("findings"), list) else []
    dispositions = _mapping(ledger.get("dispositions"))
    clusters = register.get("review_workload_clusters") if isinstance(register.get("review_workload_clusters"), list) else []
    sessions = ledger.get("review_sessions") if isinstance(ledger.get("review_sessions"), list) else []
    seconds = sum(max(0, int(_mapping(item).get("duration_seconds") or 0)) for item in sessions)
    timing = _mapping(ledger.get("operational_timing"))
    individual = sum(1 for row in findings if isinstance(row, Mapping) and row.get("review_requires_individual_attention") is True and _text(row.get("candidate_id")) not in dispositions)
    grouped = sum(1 for row in findings if isinstance(row, Mapping) and row.get("grouped_review_eligible") is True and _text(row.get("candidate_id")) not in dispositions)
    estimated_hours = float(timing.get("estimated_combined_specialist_hours") or round((individual * 12 + grouped * 2 + len(clusters) * 3 + max(1, len(findings) // 20) * 5) / 60, 2))
    return {
        "total_scanner_candidates": len(findings),
        "automated_technical_triage_completed": sum(1 for row in findings if isinstance(row, Mapping) and _text(row.get("technical_triage_verdict") or _mapping(row.get("technical_triage")).get("verdict"))),
        "individual_expert_attention_count": individual,
        "grouped_review_eligible_count": grouped,
        "cluster_count": len(clusters),
        "quality_control_sample_size": len(ledger.get("qc_required_candidate_ids") or []),
        "human_dispositions_pending": max(0, len(findings) - len(dispositions)),
        "human_dispositions_completed": len(dispositions),
        "reviewer_actions": len(ledger.get("audit_events") or []),
        "review_active_seconds": int(timing.get("review_active_minutes") or 0) * 60 or seconds,
        "assessment_runtime_seconds": int(timing.get("assessment_runtime_seconds") or 0),
        "automated_processing_duration_seconds": int(timing.get("automated_processing_duration_seconds") or 0),
        "estimated_combined_specialist_hours": estimated_hours,
        "estimated_normal_specialist_hours": estimated_hours,
        "four_hour_design_target_exceeded": estimated_hours > 4.0,
        "metrics_are_not_security_or_maturity_scores": True,
    }


def reviewer_binding(*, reviewer: str, reviewer_role: str, decision: str, decided_at: str, decision_reason: str, authorization_basis: str = "protected_admin_write_and_explicit_review_authorization") -> dict[str, Any]:
    reviewer, role, decision = _text(reviewer), _text(reviewer_role), _text(decision).casefold()
    _require(bool(reviewer), "missing_reviewer_identity")
    _require(reviewer.casefold() not in _AUTOMATION, "automation_cannot_create_final_human_approval")
    _require(bool(role), "missing_reviewer_role")
    _require(any(marker in role.casefold() for marker in ("security", "cyber", "reviewer")), "reviewer_role_not_authorized")
    _require(decision in {"approved", "rejected", "request_more_evidence"}, "invalid_review_decision")
    _require(bool(_text(decided_at)), "missing_review_timestamp")
    _require(bool(_text(decision_reason)), "reviewer_notes_required")
    _require(bool(_text(authorization_basis)), "reviewer_authorization_basis_missing")
    payload = {
        "reviewer_identity": reviewer, "reviewer_role": role, "authorization_basis": _text(authorization_basis),
        "review_decision": decision, "review_timestamp": _text(decided_at),
        "residual_risk_decision": "accepted_with_recorded_reason" if decision == "approved" else "not_accepted",
        "reviewer_notes": _text(decision_reason), "reviewer_session_requirement": "not_applicable_protected_admin_token_boundary",
        "human_action_required": True, "automation_may_not_approve": True,
    }
    payload["approval_record_id"] = "approval_" + canonical_sha256(payload)[:24]
    return payload


def build_approval_receipt(record: Mapping[str, Any], manifest: Mapping[str, Any], *, reviewer: str, reviewer_role: str, decision: str, decided_at: str, decision_reason: str, authorization_basis: str = "protected_admin_write_and_explicit_review_authorization") -> dict[str, Any]:
    identity = _identity_scope(record)
    _assert_snapshot(record, identity)
    candidates, ledger, artifacts = _candidate_contract(record), _review_contract(record, identity), _artifact_contract(record)
    review = reviewer_binding(reviewer=reviewer, reviewer_role=reviewer_role, decision=decision, decided_at=decided_at, decision_reason=decision_reason, authorization_basis=authorization_basis)
    manifest_review, manifest_artifacts = _mapping(manifest.get("review")), _mapping(manifest.get("artifact_digests"))
    _require(_text(manifest_review.get("decision")).casefold() == review["review_decision"], "approval_manifest_decision_mismatch")
    for name in _REQUIRED_ARTIFACTS:
        _require(_text(_mapping(manifest_artifacts.get(name)).get("sha256")) == artifacts[name]["sha256"], "artifact_hash_mismatch", name)
    receipt = {
        "artifact_schema": VERSION, "product_name": PRODUCT_NAME, "report_kind": REPORT_KIND,
        "package_classification": CLIENT_FINAL_CLASSIFICATION, "client_identity": identity["engagement"]["client_identity"],
        "project_identity": identity["engagement"]["project_identity"], "customer_id": identity["engagement"]["customer_id"],
        "client_id": identity["engagement"]["client_id"], "project_id": identity["engagement"]["project_id"],
        "assessment_run_id": identity["run_id"], "repository": identity["repository"],
        "assessed_repository_commit": identity["commit_sha"], "evidence_ledger_id": identity["evidence_ledger_id"],
        "authorized_scope": identity["engagement"]["authorized_scope"], "read_only_access_method": identity["engagement"]["access_method"],
        "review": review, "artifact_digests": artifacts, "pdf_sha256": artifacts["pdf"]["sha256"],
        "canonical_json_sha256": artifacts["json"]["sha256"], **ledger,
        "candidate_disposition_state_sha256": canonical_sha256(_mapping(record.get("review_work_ledger")).get("dispositions") or {}),
        "candidate_register_sha256": canonical_sha256(_register(record)), "version_truth": version_truth(record),
        "candidate_metrics": candidates, "accepted_edition_manifest_sha256": _text(manifest.get("accepted_edition_manifest_sha256")),
        "human_review_required": True, "client_delivery_authorized": review["review_decision"] == "approved",
    }
    receipt["approval_receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def validate_full_lifecycle(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    identity: dict[str, Any] = {}
    for operation in (lambda: _identity_scope(record), lambda: _scanner_contract(record), lambda: _candidate_contract(record), lambda: _artifact_contract(record)):
        try:
            value = operation()
            if not identity and isinstance(value, dict) and "run_id" in value:
                identity = value
                _assert_snapshot(record, identity)
        except ClientDeliveryContractError as exc:
            errors.append(exc.code)
    if identity:
        try:
            _review_contract(record, identity)
        except ClientDeliveryContractError as exc:
            errors.append(exc.code)
    return {
        "artifact_schema": VERSION, "status": "ready_for_explicit_human_approval" if not errors else "blocked",
        "validation_errors": sorted(set(errors)), "version_truth": version_truth(record),
        "operational_metrics": operational_metrics(record), "one_product": PRODUCT_NAME,
        "one_client_report": True, "human_review_required": True, "client_delivery_authorized": False,
    }


def validate_approval_receipt(record: Mapping[str, Any], manifest: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    review = _mapping(receipt.get("review"))
    try:
        expected = build_approval_receipt(record, manifest, reviewer=_text(review.get("reviewer_identity")), reviewer_role=_text(review.get("reviewer_role")), decision=_text(review.get("review_decision")), decided_at=_text(review.get("review_timestamp")), decision_reason=_text(review.get("reviewer_notes")), authorization_basis=_text(review.get("authorization_basis")))
    except ClientDeliveryContractError as exc:
        return {"status": "invalid", "validation_errors": [exc.code], "client_delivery_authorized": False}
    errors = []
    if canonical_sha256(receipt) != canonical_sha256(expected):
        errors.append("stale_or_mismatched_approval_receipt")
    if _text(receipt.get("approval_receipt_sha256")) != expected["approval_receipt_sha256"]:
        errors.append("approval_receipt_hash_mismatch")
    if receipt.get("client_delivery_authorized") is not True:
        errors.append("approval_incomplete_or_rejected")
    return {"status": "valid" if not errors else "invalid", "validation_errors": sorted(set(errors)), "client_delivery_authorized": not errors}


__all__ = ["CLIENT_FINAL_CLASSIFICATION", "ClientDeliveryContractError", "PRODUCT_NAME", "REPORT_KIND", "VERSION", "artifact_digests", "build_approval_receipt", "canonical_sha256", "engagement_binding", "operational_metrics", "reviewer_binding", "validate_approval_receipt", "validate_full_lifecycle", "version_truth"]
