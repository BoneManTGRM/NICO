from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

VERSION = "nico.phase11.client-workflow.v1"

REQUIRED_STEPS = (
    "submission",
    "authorization",
    "clone",
    "analysis",
    "report_generation",
    "approval",
    "delivery",
    "archive",
)
REQUIRED_SCENARIOS = {
    "happy_path",
    "retry",
    "restart",
    "cancellation",
    "large_repository",
    "mixed_language",
    "partial_scanner_availability",
    "timeout",
    "worker_interruption",
    "storage_failure",
    "duplicate_request",
}


class Phase11Error(ValueError):
    pass


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Phase11Error(f"{label} must be non-empty text")
    return value.strip()


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label).lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise Phase11Error(f"{label} must be a SHA-256 digest")
    return text


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_client_journey(journey: Mapping[str, Any]) -> dict[str, Any]:
    run_id = _text(journey.get("run_id"), "run_id")
    revision = _text(journey.get("commit_sha"), "commit_sha")
    if len(revision) != 40:
        raise Phase11Error("commit_sha must be a full commit SHA")
    steps = journey.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise Phase11Error("steps must be a list")
    by_name = {item.get("name"): item for item in steps if isinstance(item, Mapping)}
    missing = [name for name in REQUIRED_STEPS if name not in by_name]
    if missing:
        raise Phase11Error(f"missing client journey steps: {missing}")
    for name in REQUIRED_STEPS:
        step = by_name[name]
        if step.get("status") != "passed":
            raise Phase11Error(f"client journey step did not pass: {name}")
        if step.get("run_id") != run_id or step.get("commit_sha") != revision:
            raise Phase11Error(f"identity drift in client journey step: {name}")
        _sha256(step.get("evidence_sha256"), f"steps.{name}.evidence_sha256")

    if journey.get("canonical_truth_shared_by_languages") is not True:
        raise Phase11Error("English and Spanish reports must share canonical truth")
    if journey.get("approval_fail_closed") is not True or journey.get("delivery_fail_closed") is not True:
        raise Phase11Error("approval and delivery must fail closed")
    if journey.get("safe_client_errors") is not True:
        raise Phase11Error("client-visible failures must be safe and actionable")

    scenarios = journey.get("scenarios")
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, (str, bytes)):
        raise Phase11Error("scenarios must be a list")
    scenario_names = {item.get("name") for item in scenarios if isinstance(item, Mapping)}
    missing_scenarios = REQUIRED_SCENARIOS - scenario_names
    if missing_scenarios:
        raise Phase11Error(f"missing operational scenarios: {sorted(missing_scenarios)}")
    for item in scenarios:
        if not isinstance(item, Mapping):
            raise Phase11Error("scenario records must be objects")
        if item.get("status") != "passed":
            raise Phase11Error(f"scenario did not pass: {item.get('name')}")
        for key in ("duplicate_runs", "duplicate_charges", "duplicate_approvals", "duplicate_artifacts"):
            if item.get(key, 0) != 0:
                raise Phase11Error(f"{item.get('name')} produced {key}")
        _sha256(item.get("evidence_sha256"), f"scenario.{item.get('name')}.evidence_sha256")

    return {
        "schema": VERSION,
        "valid": True,
        "run_id": run_id,
        "commit_sha": revision,
        "scenario_count": len(scenarios),
        "journey_sha256": _canonical_hash(journey),
    }


def validate_phase11_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    if bundle.get("schema") != VERSION:
        raise Phase11Error("unsupported Phase 11 schema")
    journeys = bundle.get("journeys")
    if not isinstance(journeys, Sequence) or isinstance(journeys, (str, bytes)) or not journeys:
        raise Phase11Error("at least one end-to-end client journey is required")
    validated = [validate_client_journey(item) for item in journeys if isinstance(item, Mapping)]
    if len(validated) != len(journeys):
        raise Phase11Error("every journey must be an object")
    runbook = bundle.get("operational_runbook")
    if not isinstance(runbook, Mapping):
        raise Phase11Error("operational_runbook is required")
    for key in ("monitoring", "incident_response", "rollback", "recovery", "support", "data_retention"):
        _text(runbook.get(key), f"operational_runbook.{key}")
    if bundle.get("legacy_paths_quarantined") is not True:
        raise Phase11Error("legacy report and scanner paths must be removed or quarantined")
    result = {
        "schema": VERSION,
        "valid": True,
        "journeys": validated,
        "legacy_paths_quarantined": True,
        "operational_runbook_complete": True,
    }
    result["bundle_sha256"] = _canonical_hash(result)
    return result


__all__ = ["VERSION", "Phase11Error", "validate_client_journey", "validate_phase11_bundle"]
