from __future__ import annotations

from copy import deepcopy

import pytest

from nico.phase11_client_workflow_v1 import VERSION, Phase11Error, validate_phase11_bundle

SHA = "a" * 40
DIGEST = "b" * 64
STEPS = (
    "submission", "authorization", "clone", "analysis", "report_generation", "approval", "delivery", "archive"
)
SCENARIOS = (
    "happy_path", "retry", "restart", "cancellation", "large_repository", "mixed_language",
    "partial_scanner_availability", "timeout", "worker_interruption", "storage_failure", "duplicate_request"
)


def _bundle() -> dict:
    run_id = "run-1"
    journey = {
        "run_id": run_id,
        "commit_sha": SHA,
        "steps": [
            {"name": name, "status": "passed", "run_id": run_id, "commit_sha": SHA, "evidence_sha256": DIGEST}
            for name in STEPS
        ],
        "canonical_truth_shared_by_languages": True,
        "approval_fail_closed": True,
        "delivery_fail_closed": True,
        "safe_client_errors": True,
        "scenarios": [
            {
                "name": name,
                "status": "passed",
                "duplicate_runs": 0,
                "duplicate_charges": 0,
                "duplicate_approvals": 0,
                "duplicate_artifacts": 0,
                "evidence_sha256": DIGEST,
            }
            for name in SCENARIOS
        ],
    }
    return {
        "schema": VERSION,
        "journeys": [journey],
        "legacy_paths_quarantined": True,
        "operational_runbook": {
            "monitoring": "Metrics and alerts",
            "incident_response": "Triage and escalation",
            "rollback": "Immutable rollback procedure",
            "recovery": "Database and artifact recovery",
            "support": "Client support diagnostics",
            "data_retention": "Retention and deletion policy",
        },
    }


def test_phase11_complete_bundle_passes() -> None:
    result = validate_phase11_bundle(_bundle())
    assert result["valid"] is True
    assert len(result["bundle_sha256"]) == 64


def test_phase11_rejects_identity_drift() -> None:
    bundle = _bundle()
    bundle["journeys"][0]["steps"][3]["commit_sha"] = "c" * 40
    with pytest.raises(Phase11Error, match="identity drift"):
        validate_phase11_bundle(bundle)


def test_phase11_rejects_duplicate_delivery_effects() -> None:
    bundle = _bundle()
    bundle["journeys"][0]["scenarios"][-1]["duplicate_artifacts"] = 1
    with pytest.raises(Phase11Error, match="duplicate_artifacts"):
        validate_phase11_bundle(bundle)


def test_phase11_rejects_missing_scenario() -> None:
    bundle = _bundle()
    bundle["journeys"][0]["scenarios"] = bundle["journeys"][0]["scenarios"][:-1]
    with pytest.raises(Phase11Error, match="missing operational scenarios"):
        validate_phase11_bundle(bundle)


def test_phase11_rejects_open_delivery_gate() -> None:
    bundle = _bundle()
    bundle["journeys"][0]["delivery_fail_closed"] = False
    with pytest.raises(Phase11Error, match="fail closed"):
        validate_phase11_bundle(bundle)


def test_phase11_rejects_incomplete_runbook() -> None:
    bundle = _bundle()
    del bundle["operational_runbook"]["recovery"]
    with pytest.raises(Phase11Error, match="recovery"):
        validate_phase11_bundle(bundle)
