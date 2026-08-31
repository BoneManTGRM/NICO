from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_review_decision_v1 import report_package_from_record
from nico.decision_grade_accepted_edition_guard_v1 import (
    current_report_artifact_digest,
    current_report_artifact_digests,
    validate_accepted_edition,
)
from nico.strategic_human_evidence_v1 import (
    VERSION as HUMAN_EVIDENCE_VERSION,
    normalize_strategic_human_evidence,
    verify_strategic_human_evidence,
)

VERSION = "nico.comprehensive_run_record.v5"
LEGACY_VERSION = "nico.comprehensive_run_record.v2"
FINAL_REPORT_STAGE_ID = "final_comprehensive_report_generation"
TERMINAL_STATUSES = {"review_required", "approved", "rejected", "failed", "blocked"}
ACTIVE_STAGE_STATUSES = {"queued", "running", "pending", "planned", "in_progress"}
SUCCESS_STAGE_STATUSES = {"complete", "completed", "passed", "review_required"}
_REVIEW_DECISIONS = {"approved", "rejected", "request_more_evidence"}


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def _canonical_hash(payload: Any) -> str:
    """Hash canonical JSON without materializing a second full JSON string."""

    encoder = json.JSONEncoder(
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha256()
    for chunk in encoder.iterencode(payload):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def _copy_record_for_update(record: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a run record while retaining completed stage payloads by reference.

    Stage results are append-only canonical evidence. Deep-copying the entire
    retained evidence tree on every continuation multiplies peak memory once
    scanner candidates and report artifacts are present. Copy the mutable map
    boundary, while preserving the prior immutable stage values. Other fields
    remain deeply isolated.
    """

    copied: dict[str, Any] = {}
    for key, value in record.items():
        if key == "stage_results" and isinstance(value, Mapping):
            copied[key] = dict(value)
        else:
            copied[key] = deepcopy(value)
    copied.setdefault("stage_results", {})
    return copied


def _copy_stage_result(stage_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve normal executor isolation without cloning the final package."""

    if stage_id != FINAL_REPORT_STAGE_ID:
        return deepcopy(dict(result))
    copied: dict[str, Any] = {}
    for key, value in result.items():
        if key == "report_package" and isinstance(value, Mapping):
            copied[key] = dict(value)
        else:
            copied[key] = deepcopy(value)
    return copied


def create_comprehensive_run_record(
    *,
    run_id: str,
    repository: str,
    commit_sha: str,
    evidence_ledger_id: str,
    customer_id: str,
    project_id: str,
    authorized: bool,
    assessment_depth: str = "strategic",
    report_language: str = "en",
    human_evidence: Any = None,
    repository_provider: str = "",
    provider_access_mode: str = "",
    provider_credential_used: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not authorized:
        raise ValueError("explicit_authorization_required")
    created_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    identity = {
        "run_id": _required(run_id, "run_id"),
        "repository": _required(repository, "repository"),
        "commit_sha": _required(commit_sha, "commit_sha"),
        "evidence_ledger_id": _required(evidence_ledger_id, "evidence_ledger_id"),
        "customer_id": _required(customer_id, "customer_id"),
        "project_id": _required(project_id, "project_id"),
        "assessment_depth": _required(assessment_depth, "assessment_depth"),
        "report_language": _required(report_language, "report_language"),
    }
    normalized_human_evidence = normalize_strategic_human_evidence(human_evidence)
    record = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "identity": identity,
        "human_evidence": normalized_human_evidence,
        "status": "ready",
        "current_stage": None,
        "completed_stages": [],
        "stage_results": {},
        "progress_percent": 0.0,
        "created_at": created_at,
        "updated_at": created_at,
        "revision": 1,
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "terminal": False,
    }
    normalized_provider = str(repository_provider or "").strip()
    normalized_access_mode = str(provider_access_mode or "").strip()
    if normalized_provider:
        record["repository_provider"] = normalized_provider
    if normalized_access_mode:
        if not (
            normalized_access_mode == "anonymous_public"
            and provider_credential_used is False
        ) and not (
            normalized_access_mode == "authenticated_read_only"
            and provider_credential_used is True
        ):
            raise ValueError("provider_access_binding_invalid")
        record["provider_access_mode"] = normalized_access_mode
        record["provider_credential_used"] = provider_credential_used
    record["integrity_sha256"] = _record_hash(record)
    return record


def _record_hash(record: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in record.items()
        if key != "integrity_sha256"
    }
    return _canonical_hash(payload)


def _manifest_hash_valid(candidate: Mapping[str, Any]) -> bool:
    payload = deepcopy(dict(candidate))
    claimed = str(payload.pop("accepted_edition_manifest_sha256", "") or "")
    return bool(claimed and claimed == _canonical_hash(payload))


def _certificate_hash_valid(review: Mapping[str, Any]) -> bool:
    payload = deepcopy(dict(review))
    claimed = str(payload.pop("approval_certificate_sha256", "") or "")
    return bool(claimed and claimed == _canonical_hash(payload))


def _review_manifest_errors(
    record: Mapping[str, Any],
    candidate: Any,
) -> list[str]:
    if not isinstance(candidate, Mapping):
        return ["review_manifest_required"]
    errors: list[str] = []
    if list(candidate.get("validation_errors") or []):
        errors.append("review_manifest_contains_validation_errors")
    if not _manifest_hash_valid(candidate):
        errors.append("review_manifest_hash_mismatch")
    review = candidate.get("review") if isinstance(candidate.get("review"), Mapping) else {}
    decision = str(review.get("decision") or "").casefold()
    if decision not in _REVIEW_DECISIONS:
        errors.append("review_decision_invalid")
    if not _certificate_hash_valid(review):
        errors.append("review_certificate_hash_mismatch")

    package = report_package_from_record(record)
    if not package:
        errors.append("review_report_package_required")
        return errors
    expected_digests = current_report_artifact_digests(package)
    expected_digest = current_report_artifact_digest(package)
    required_digests = {"markdown", "html", "pdf", "json"}
    if any(
        package.get(key) not in (None, "")
        for key in (
            "artifact_manifest",
            "evidence_manifest_json",
            "evidence_manifest_sha256",
            "draft_artifact_identity",
        )
    ):
        required_digests.add("evidence_manifest")
    if set(expected_digests) != required_digests:
        errors.append("review_report_artifacts_incomplete")
    if candidate.get("artifact_digests") != expected_digests:
        errors.append("review_artifact_digests_mismatch")
    if str(candidate.get("report_artifact_digest") or "") != expected_digest:
        errors.append("review_report_digest_mismatch")
    if str(review.get("report_artifact_digest") or "") != expected_digest:
        errors.append("review_certificate_report_digest_mismatch")

    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    for field in (
        "repository",
        "commit_sha",
        "run_id",
        "report_language",
        "assessment_depth",
    ):
        if str(candidate.get(field) or "") != str(identity.get(field) or ""):
            errors.append(f"review_identity_mismatch:{field}")
    for field in ("tree_sha", "scanner_run_id", "evidence_bundle_hash"):
        if not str(candidate.get(field) or "").strip():
            errors.append(f"review_identity_missing:{field}")

    if decision == "approved":
        validation = validate_accepted_edition(package, candidate)
        errors.extend(str(item) for item in validation.get("validation_errors") or [])
    else:
        if candidate.get("accepted_edition") is not False:
            errors.append("nonapproval_must_not_create_accepted_edition")
        if candidate.get("client_delivery_allowed") is not False:
            errors.append("nonapproval_must_block_delivery")
        if str(candidate.get("delivery_status") or "") != "blocked":
            errors.append("nonapproval_delivery_status_invalid")
    return sorted(set(errors))


def _validate_record(
    record: dict[str, Any],
    *,
    require_strategic_context: bool,
) -> list[str]:
    violations: list[str] = []
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    fields = [
        "run_id",
        "repository",
        "commit_sha",
        "evidence_ledger_id",
        "customer_id",
        "project_id",
    ]
    if require_strategic_context:
        fields.extend(["assessment_depth", "report_language"])
    for field in fields:
        if not str(identity.get(field) or "").strip():
            violations.append(f"{field}_required")
    if record.get("service_id") != "comprehensive":
        violations.append("service_id_must_be_comprehensive")
    if record.get("human_review_required") is not True:
        violations.append("human_review_required")

    status = str(record.get("status") or "").lower()
    delivery_allowed = record.get("client_delivery_allowed") is True
    if status == "approved":
        if record.get("human_review_completed") is not True:
            violations.append("approved_run_requires_completed_review")
        review_errors = _review_manifest_errors(record, record.get("accepted_edition"))
        violations.extend(f"accepted_edition:{item}" for item in review_errors)
        if delivery_allowed:
            accepted = (
                record.get("accepted_edition")
                if isinstance(record.get("accepted_edition"), Mapping)
                else {}
            )
            if accepted.get("client_delivery_allowed") is not False:
                violations.append("approved_delivery_accepted_edition_must_remain_immutable")
            if str(accepted.get("delivery_status") or "") != "pending_authorization":
                violations.append("approved_delivery_accepted_edition_status_changed")
            try:
                from nico.comprehensive_delivery_authorization_v1 import (
                    validate_delivery_authorization,
                )

                authorization_validation = validate_delivery_authorization(
                    record,
                    accepted,
                    record.get("delivery_authorization"),
                )
                violations.extend(
                    f"delivery_authorization:{item}"
                    for item in authorization_validation.get("validation_errors") or []
                )
            except (TypeError, ValueError) as exc:
                violations.append(
                    "delivery_authorization:validation_failed:"
                    + str(exc).split(":", 1)[0]
                )
            if not isinstance(record.get("approved_delivery_package"), Mapping):
                violations.append("approved_delivery_package_required")
    elif delivery_allowed:
        violations.append("client_delivery_must_remain_blocked")

    review_decision = record.get("review_decision")
    review_history_value = record.get("review_history")
    review_history = review_history_value if isinstance(review_history_value, list) else []
    if review_history_value is not None and not isinstance(review_history_value, list):
        violations.append("review_history_invalid")
    if review_history:
        final_history_entry = review_history[-1]
        if not isinstance(review_decision, Mapping):
            violations.append("review_history_requires_review_decision")
        elif not isinstance(final_history_entry, Mapping) or dict(
            final_history_entry
        ) != dict(review_decision):
            violations.append("review_decision_history_mismatch")
    if status in {"approved", "rejected"}:
        if not review_history:
            violations.append(f"{status}_review_history_required")
        if not isinstance(review_decision, Mapping):
            violations.append(f"{status}_review_decision_required")

    if review_decision is not None:
        review_errors = _review_manifest_errors(record, review_decision)
        violations.extend(f"review_decision:{item}" for item in review_errors)
        review_decision_mapping = (
            review_decision if isinstance(review_decision, Mapping) else {}
        )
        review = review_decision_mapping.get("review")
        review = review if isinstance(review, Mapping) else {}
        decision = str(review.get("decision") or "").casefold()
        expected_status = {
            "approved": "approved",
            "rejected": "rejected",
            "request_more_evidence": "review_required",
        }.get(decision)
        if expected_status and status != expected_status:
            violations.append("review_decision_status_mismatch")
        if not review_history:
            violations.append("review_decision_history_required")
        else:
            final_history_entry = review_history[-1]
            if (
                not isinstance(final_history_entry, Mapping)
                or dict(final_history_entry) != dict(review_decision_mapping)
            ):
                violations.append("review_decision_history_mismatch")
        accepted = record.get("accepted_edition")
        if decision == "approved":
            if not isinstance(accepted, Mapping) or dict(accepted) != dict(
                review_decision_mapping
            ):
                violations.append("approved_accepted_edition_history_mismatch")
        elif isinstance(accepted, Mapping):
            violations.append("nonapproval_must_not_retain_accepted_edition")

    accepted = record.get("accepted_edition")
    if status == "approved" and isinstance(accepted, Mapping):
        if not review_history or not isinstance(review_history[-1], Mapping) or dict(
            accepted
        ) != dict(review_history[-1]):
            violations.append("approved_accepted_edition_history_mismatch")

    if require_strategic_context:
        human_evidence = record.get("human_evidence")
        if not isinstance(human_evidence, dict):
            violations.append("human_evidence_required")
        else:
            if human_evidence.get("artifact_schema") != HUMAN_EVIDENCE_VERSION:
                violations.append("human_evidence_schema_invalid")
            if not verify_strategic_human_evidence(human_evidence):
                violations.append("human_evidence_hash_mismatch")
    completed = list(record.get("completed_stages") or [])
    if completed != list(COMPREHENSIVE_STAGES[: len(completed)]):
        violations.append("completed_stages_must_be_ordered_prefix")
    if len(set(completed)) != len(completed):
        violations.append("duplicate_completed_stages")
    expected_progress = round((len(completed) / len(COMPREHENSIVE_STAGES)) * 100, 2)
    if float(record.get("progress_percent") or 0.0) != expected_progress:
        violations.append("progress_must_match_completed_stages")
    if record.get("integrity_sha256") != _record_hash(record):
        violations.append("integrity_hash_mismatch")
    terminal = status in TERMINAL_STATUSES
    if bool(record.get("terminal")) != terminal:
        violations.append("terminal_flag_mismatch")
    return violations


def validate_comprehensive_run_record(record: dict[str, Any]) -> dict[str, Any]:
    schema = str(record.get("artifact_schema") or "")
    violations = _validate_record(
        record,
        require_strategic_context=schema != LEGACY_VERSION,
    )
    return {
        "status": "valid" if not violations else "invalid",
        "violations": violations,
    }


def apply_comprehensive_stage_result(
    record: dict[str, Any],
    *,
    stage_id: str,
    result: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    updated = _copy_record_for_update(record)
    completed = list(updated["completed_stages"])
    expected_stage = (
        COMPREHENSIVE_STAGES[len(completed)]
        if len(completed) < len(COMPREHENSIVE_STAGES)
        else None
    )
    if stage_id != expected_stage:
        raise ValueError(f"unexpected_stage:{stage_id}:expected:{expected_stage}")
    identity = updated["identity"]
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        supplied = str(result.get(field) or identity[field]).strip()
        if supplied != identity[field]:
            raise ValueError(f"{stage_id}:{field}_identity_drift")
    status = str(result.get("status") or "complete").strip().lower()
    normalized = {
        **_copy_stage_result(stage_id, result),
        "stage_id": stage_id,
        "status": status,
    }
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        normalized[field] = identity[field]
    normalized["assessment_depth"] = identity["assessment_depth"]
    normalized["report_language"] = identity["report_language"]
    normalized["human_review_required"] = True
    normalized["client_delivery_allowed"] = False
    updated["stage_results"][stage_id] = normalized
    updated["current_stage"] = stage_id

    if status in SUCCESS_STAGE_STATUSES:
        completed.append(stage_id)
        updated["completed_stages"] = completed
        updated["status"] = (
            "review_required"
            if len(completed) == len(COMPREHENSIVE_STAGES)
            else "running"
        )
    elif status in ACTIVE_STAGE_STATUSES:
        updated["status"] = "running"
    else:
        updated["status"] = "blocked"

    updated["progress_percent"] = round(
        (len(completed) / len(COMPREHENSIVE_STAGES)) * 100,
        2,
    )
    updated["updated_at"] = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["terminal"] = updated["status"] in TERMINAL_STATUSES
    updated["human_review_required"] = True
    updated["human_review_completed"] = False
    updated["client_delivery_allowed"] = False
    updated["integrity_sha256"] = _record_hash(updated)
    return updated


def apply_comprehensive_review_decision(
    record: dict[str, Any],
    *,
    manifest: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if str(record.get("status") or "").lower() != "review_required":
        raise ValueError("review_decision_requires_review_required_run")
    if list(record.get("completed_stages") or []) != list(COMPREHENSIVE_STAGES):
        raise ValueError("review_decision_requires_complete_stage_sequence")
    errors = _review_manifest_errors(record, manifest)
    if errors:
        raise ValueError("invalid_review_manifest:" + ",".join(errors))

    updated = _copy_record_for_update(record)
    candidate = deepcopy(dict(manifest))
    review = candidate.get("review") if isinstance(candidate.get("review"), Mapping) else {}
    decision = str(review.get("decision") or "").casefold()
    status = {
        "approved": "approved",
        "rejected": "rejected",
        "request_more_evidence": "review_required",
    }[decision]
    history = [
        deepcopy(dict(item))
        for item in updated.get("review_history") or []
        if isinstance(item, Mapping)
    ]
    history.append(candidate)
    updated["review_history"] = history
    updated["review_decision"] = candidate
    if decision == "approved":
        updated["accepted_edition"] = candidate
    else:
        updated.pop("accepted_edition", None)
    updated.pop("approved_delivery_package", None)
    updated.pop("delivery_authorization", None)
    package = report_package_from_record(updated)
    updated["review_context"] = {
        "report_id": str(package.get("report_id") or ""),
        "pdf_filename": str(package.get("pdf_filename") or ""),
        "report_regenerated_during_review": False,
        "artifact_digest": str(candidate.get("report_artifact_digest") or ""),
    }
    updated["status"] = status
    updated["terminal"] = True
    updated["human_review_required"] = True
    updated["human_review_completed"] = decision in {"approved", "rejected"}
    # Human approval binds the exact accepted edition. Client delivery remains a
    # distinct, explicitly authorized transition with its own audit receipt.
    updated["client_delivery_allowed"] = False
    updated["updated_at"] = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["integrity_sha256"] = _record_hash(updated)
    final_validation = validate_comprehensive_run_record(updated)
    if final_validation["status"] != "valid":
        raise ValueError(
            "invalid_reviewed_run_record:" + ",".join(final_validation["violations"])
        )
    return updated


def restore_comprehensive_run_record(payload: dict[str, Any]) -> dict[str, Any]:
    restored = _copy_record_for_update(payload)
    validation = validate_comprehensive_run_record(restored)
    if validation["status"] != "valid":
        raise ValueError(
            "invalid_persisted_run_record:" + ",".join(validation["violations"])
        )
    if restored.get("artifact_schema") == LEGACY_VERSION:
        identity = restored["identity"]
        identity.setdefault("assessment_depth", "not_recorded")
        identity.setdefault("report_language", "not_recorded")
        restored["human_evidence"] = normalize_strategic_human_evidence(None)
        restored.setdefault("human_review_completed", False)
        restored["artifact_schema"] = VERSION
        restored["integrity_sha256"] = _record_hash(restored)
        upgraded = validate_comprehensive_run_record(restored)
        if upgraded["status"] != "valid":
            raise ValueError(
                "invalid_upgraded_run_record:" + ",".join(upgraded["violations"])
            )
    return restored


__all__ = [
    "ACTIVE_STAGE_STATUSES",
    "FINAL_REPORT_STAGE_ID",
    "SUCCESS_STAGE_STATUSES",
    "TERMINAL_STATUSES",
    "VERSION",
    "apply_comprehensive_review_decision",
    "apply_comprehensive_stage_result",
    "create_comprehensive_run_record",
    "restore_comprehensive_run_record",
    "validate_comprehensive_run_record",
]
