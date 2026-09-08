"""Re-enter the ordinary scanner stage after an owner-authorized checkout repair."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record
from nico.storage import STORE

VERSION = "nico.private_checkout_continuation.v1"
STAGE = "dependency_security_static_analysis"
MARKER = "private_checkout_recovery_v1"


def resume_recovered_private_checkout(record):
    """Do not declare a stage complete: let its existing executor evaluate the scan."""
    if record.get("status") != "blocked" or record.get("current_stage") != STAGE:
        return record
    stage = record.get("stage_results", {}).get(STAGE, {})
    history = record.get("recovery_history") or []
    if (stage.get("reason") != "snapshot_scanner_not_verified"
            or any(item.get("artifact_schema") == VERSION for item in history)
            or record.get("completed_stages") != list(COMPREHENSIVE_STAGES[:COMPREHENSIVE_STAGES.index(STAGE)])):
        return record
    scan = STORE.get("scanner_runs", stage.get("scan_id")) or {}
    marker = scan.get(MARKER) or {}
    previous = marker.get("previous_failure") or {}
    identity = record.get("identity") or {}
    snapshot = record.get("stage_results", {}).get("immutable_repository_snapshot", {}).get("snapshot", {})
    if (scan.get("status") != "complete" or scan.get("snapshot_match") is not True
            or scan.get("actual_commit_sha") != identity.get("commit_sha")
            or marker.get("attempt") != 1 or marker.get("automatic_retry") is not False
            or not marker.get("requested_at")
            or previous.get("status") != "unavailable"
            or previous.get("current_stage") != "snapshot_verification_failed"
            or previous.get("scanner_results") != [] or previous.get("tools_run") != []
            or previous.get("actual_commit_sha") != "" or previous.get("snapshot_match") is not False
            or not previous.get("authorized_by") or not previous.get("authorization_scope")
            or snapshot.get("access_mode", snapshot.get("provider_access_mode")) != "authenticated_read_only"
            or snapshot.get("credential_used", snapshot.get("provider_credential_used")) is not True
            or snapshot.get("commit_sha") != identity.get("commit_sha")
            or snapshot.get("repository") != identity.get("repository")
            or not snapshot.get("snapshot_id")):
        return record
    expected = {key: identity.get(key) for key in ("run_id", "customer_id", "project_id", "repository")}
    expected.update(scan_id=stage.get("scan_id"), snapshot_id=snapshot["snapshot_id"], snapshot_commit_sha=identity.get("commit_sha"))
    if any(not value or scan.get(key) != value or previous.get(key) != value for key, value in expected.items()):
        return record
    fingerprint = hashlib.sha256(json.dumps(previous, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if marker.get("failure_fingerprint") != fingerprint:
        return record
    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    updated = deepcopy(record)
    updated["recovery_history"] = [*deepcopy(history), {
        "artifact_schema": VERSION, "source_failed_stage": STAGE,
        "previous_stage_result": deepcopy(stage), "scan_id": scan["scan_id"],
        "failure_fingerprint": fingerprint, "recovered_at": datetime.now(UTC).isoformat(),
        "human_review_required": True, "client_delivery_allowed": False,
    }]
    # Retain the failed stage's scan reference so the executor cannot mint another scan.
    updated.update(status="running", terminal=False, revision=int(record["revision"]) + 1,
                   updated_at=datetime.now(UTC).isoformat())
    updated["integrity_sha256"] = _record_hash(updated)
    return updated
