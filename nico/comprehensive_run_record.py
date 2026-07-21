from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES

VERSION = "nico.comprehensive_run_record.v2"
TERMINAL_STATUSES = {"review_required", "approved", "rejected", "failed", "blocked"}
ACTIVE_STAGE_STATUSES = {"queued", "running", "pending", "planned", "in_progress"}
SUCCESS_STAGE_STATUSES = {"complete", "completed", "passed", "review_required"}


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_comprehensive_run_record(
    *,
    run_id: str,
    repository: str,
    commit_sha: str,
    evidence_ledger_id: str,
    customer_id: str,
    project_id: str,
    authorized: bool,
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
    }
    record = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "identity": identity,
        "status": "ready",
        "current_stage": None,
        "completed_stages": [],
        "stage_results": {},
        "progress_percent": 0.0,
        "created_at": created_at,
        "updated_at": created_at,
        "revision": 1,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "terminal": False,
    }
    record["integrity_sha256"] = _record_hash(record)
    return record


def _record_hash(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    payload.pop("integrity_sha256", None)
    return _canonical_hash(payload)


def validate_comprehensive_run_record(record: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id"):
        if not str(identity.get(field) or "").strip():
            violations.append(f"{field}_required")
    if record.get("service_id") != "comprehensive":
        violations.append("service_id_must_be_comprehensive")
    if record.get("human_review_required") is not True:
        violations.append("human_review_required")
    if record.get("client_delivery_allowed") is not False:
        violations.append("client_delivery_must_remain_blocked")
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
    terminal = str(record.get("status") or "").lower() in TERMINAL_STATUSES
    if bool(record.get("terminal")) != terminal:
        violations.append("terminal_flag_mismatch")
    return {"status": "valid" if not violations else "invalid", "violations": violations}


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
    updated = deepcopy(record)
    completed = list(updated["completed_stages"])
    expected_stage = COMPREHENSIVE_STAGES[len(completed)] if len(completed) < len(COMPREHENSIVE_STAGES) else None
    if stage_id != expected_stage:
        raise ValueError(f"unexpected_stage:{stage_id}:expected:{expected_stage}")
    identity = updated["identity"]
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        supplied = str(result.get(field) or identity[field]).strip()
        if supplied != identity[field]:
            raise ValueError(f"{stage_id}:{field}_identity_drift")
    status = str(result.get("status") or "complete").strip().lower()
    normalized = {**deepcopy(result), "stage_id": stage_id, "status": status}
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        normalized[field] = identity[field]
    normalized["human_review_required"] = True
    normalized["client_delivery_allowed"] = False
    updated["stage_results"][stage_id] = normalized
    updated["current_stage"] = stage_id

    if status in SUCCESS_STAGE_STATUSES:
        completed.append(stage_id)
        updated["completed_stages"] = completed
        updated["status"] = "review_required" if len(completed) == len(COMPREHENSIVE_STAGES) else "running"
    elif status in ACTIVE_STAGE_STATUSES:
        updated["status"] = "running"
    else:
        updated["status"] = "blocked"

    updated["progress_percent"] = round((len(completed) / len(COMPREHENSIVE_STAGES)) * 100, 2)
    updated["updated_at"] = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["terminal"] = updated["status"] in TERMINAL_STATUSES
    updated["human_review_required"] = True
    updated["client_delivery_allowed"] = False
    updated["integrity_sha256"] = _record_hash(updated)
    return updated


def restore_comprehensive_run_record(payload: dict[str, Any]) -> dict[str, Any]:
    restored = deepcopy(payload)
    validation = validate_comprehensive_run_record(restored)
    if validation["status"] != "valid":
        raise ValueError("invalid_persisted_run_record:" + ",".join(validation["violations"]))
    return restored


__all__ = [
    "ACTIVE_STAGE_STATUSES",
    "SUCCESS_STAGE_STATUSES",
    "TERMINAL_STATUSES",
    "VERSION",
    "apply_comprehensive_stage_result",
    "create_comprehensive_run_record",
    "restore_comprehensive_run_record",
    "validate_comprehensive_run_record",
]
