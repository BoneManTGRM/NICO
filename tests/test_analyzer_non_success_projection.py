import pytest

from nico.phase14_analyzer_evidence_v1 import (
    analyzer_report_projection,
    analyzer_ui_projection,
    classify_status,
    reconcile_analyzers,
)
from nico.phase15_production_integration_v1 import (
    integrate_production_truth,
    normalize_production_scanner_records,
)

SHA = "a" * 40


@pytest.mark.parametrize("status", ["unavailable", "blocked", "skipped", "not_assessed", "incomplete"])
@pytest.mark.parametrize("capture_complete", [False, True, None])
def test_explicit_non_success_state_survives_capture_metadata(status, capture_complete):
    record = {
        "scanner": "eslint", "status": status, "commit_sha": SHA,
        "capture_complete": capture_complete,
        "failure_cause": "capture truncated after worker timeout",
    }
    assert classify_status(record) == status


def test_unperformed_live_shape_stays_unavailable_in_report_and_ui():
    # Minimal independently retained shape from the failed production proof:
    # no invocation, no raw artifact, and an explicit unavailable outcome.
    raw = {
        "tool": "eslint", "status": "unavailable", "commit_sha": SHA,
        "verified_complete": False, "output_capture_complete": False,
        "execution_provenance": {"invocation_receipts": []},
    }
    [record] = normalize_production_scanner_records([raw], expected_sha=SHA)
    assert record["capture_complete"] is False
    reconciliation = reconcile_analyzers(
        [record], expected_sha=SHA, required_scanners=["eslint"],
    )
    report = analyzer_report_projection(reconciliation)
    ui = analyzer_ui_projection(reconciliation)
    assert report["status_counts"] == {"unavailable": 1}
    assert report["analyzers"][0]["status"] == ui["rows"][0]["status"] == "unavailable"
    assert report["acceptance_ready"] is False
    assert ui["state"] == "blocked"
    assert ui["rows"][0]["passes"] == "0/2"
    assert report["analyzers"][0]["client_defect_allowed"] is False
    assert report["analyzers"][0]["artifact_sha256"] == []
    assert "unavailable" in report["analyzers"][0]["failure_cause"].lower()
    assert ui["rows"][0]["next_action"]
    assert "worker boundary" in ui["rows"][0]["next_action"]
    assert "Persist the complete output" not in ui["rows"][0]["next_action"]


@pytest.mark.parametrize("status", ["unavailable", "blocked", "skipped", "not_assessed", "incomplete"])
def test_non_success_breaks_prior_success_without_execution_or_delivery_credit(status):
    successes = [
        {"scanner": "eslint", "status": "completed", "commit_sha": SHA,
         "capture_complete": True, "artifact_sha256": digest * 64, "run_sequence": run}
        for run, digest in [(1, "b"), (2, "c")]
    ]
    result = reconcile_analyzers(
        [*successes, {"scanner": "eslint", "status": status, "commit_sha": SHA,
                      "capture_complete": False, "run_sequence": 3,
                      "confirmed_client_defect": True}],
        expected_sha=SHA, required_scanners=["eslint"],
    )
    [analyzer] = result["analyzers"]
    assert analyzer["status"] == status
    assert analyzer["successful_passes"] == 2
    assert analyzer["consecutive_successful_passes"] == 0
    assert analyzer["acceptance_ready"] is False
    assert analyzer["client_defect_allowed"] is False
    assert analyzer["artifact_sha256"] == []
    assert analyzer["failure_cause"] and analyzer["assurance_impact"] and analyzer["remediation"]
    assert result["acceptance_ready"] is False


def test_integrated_unavailable_projection_remains_blocked_without_score_or_approval_change():
    payload = {
        "commit_sha": SHA, "technical_score": 71, "evidence_adjusted_score": 67,
        "approval_status": "pending_human_approval", "client_delivery_allowed": False,
        "scanner_execution_records": [
            {"tool": "eslint", "status": "unavailable", "commit_sha": SHA,
             "verified_complete": False, "output_capture_complete": False},
        ],
    }
    result = integrate_production_truth(payload)
    row = next(r for r in result["analyzer_evidence_ui"]["rows"] if r["scanner"] == "eslint")
    assert row["status"] == "unavailable"
    assert row["ready"] is False
    assert result["delivery_gate"]["analyzer_evidence_ready"] is False
    for key in ["technical_score", "evidence_adjusted_score", "approval_status", "client_delivery_allowed"]:
        assert result[key] == payload[key]


@pytest.mark.parametrize("status", ["failed", "timed_out", "capture_truncated", "unsupported_target"])
def test_existing_failure_states_keep_their_identity(status):
    assert classify_status({"status": status, "capture_complete": False}) == status

def test_old_integrated_payload_rebuilds_projection_from_retained_raw_records():
    raw = {"tool": "eslint", "status": "unavailable", "commit_sha": SHA,
           "verified_complete": False, "output_capture_complete": False}
    old = {
        "commit_sha": SHA, "scanner_execution_records": [raw],
        "phase15_production_integration": {
            "version": "nico.phase15.production-integration.v2",
            "analyzer_contract_applied": True,
        },
        "evidence_health_summary": {"scanner_records": [
            {"scanner": "eslint", "status": "capture_truncated",
             "successful_passes": 0, "consecutive_successful_passes": 0},
        ]},
        "analyzer_evidence_ui": {"rows": [
            {"scanner": "eslint", "status": "capture_truncated"},
        ]},
    }
    result = integrate_production_truth(old)
    row = next(r for r in result["analyzer_evidence_ui"]["rows"] if r["scanner"] == "eslint")
    analyzer = next(r for r in result["analyzer_evidence_report"]["analyzers"] if r["scanner"] == "eslint")
    assert row["status"] == analyzer["status"] == "unavailable"
    assert analyzer["run_count"] == 1
    assert result["phase15_production_integration"]["version"] == "nico.phase15.production-integration.v3"
    assert result["scanner_execution_records"] == [raw]
    assert old["analyzer_evidence_ui"]["rows"][0]["status"] == "capture_truncated"
    assert integrate_production_truth(result)["analyzer_evidence_report"] == result["analyzer_evidence_report"]

@pytest.mark.parametrize("status", [
    "unavailable", "blocked", "skipped", "not_assessed", "incomplete",
    "timed_out", "capture_truncated", "unsupported_target",
])
def test_bandit_success_metadata_cannot_override_explicit_non_success(status):
    raw = {
        "scanner": "bandit", "status": status, "commit_sha": SHA,
        "raw_exit_code": 1, "artifact_sha256": "b" * 64,
        "verified_complete": True, "json_parseable": True,
    }
    [record] = normalize_production_scanner_records([raw], expected_sha=SHA)
    assert record["status"] == status
    result = reconcile_analyzers([record], expected_sha=SHA, required_scanners=["bandit"])
    assert result["acceptance_ready"] is False
    assert result["analyzers"][0]["consecutive_successful_passes"] == 0
    assert result["analyzers"][0]["client_defect_allowed"] is False

@pytest.mark.parametrize(("status", "expected"), [
    ("not_applicable", "not_applicable"), ("n/a", "not_applicable"),
    ("na", "not_applicable"), ("timeout", "timed_out"),
    ("timedout", "timed_out"), ("truncated", "capture_truncated"),
    ("unsupported", "unsupported_target"),
])
def test_bandit_declared_failure_and_applicability_aliases_survive_success_metadata(status, expected):
    [record] = normalize_production_scanner_records([{
        "scanner": "bandit", "status": status, "commit_sha": SHA,
        "scope_reason": "No Python source files are present.",
        "raw_exit_code": 1, "artifact_sha256": "b" * 64,
        "verified_complete": True, "json_parseable": True,
    }], expected_sha=SHA)
    assert record["status"] == expected
    result = reconcile_analyzers([record], expected_sha=SHA, required_scanners=["bandit"])
    assert result["analyzers"][0]["client_defect_allowed"] is False
    if expected == "not_applicable":
        assert result["analyzers"][0]["not_applicable_reason"] == "No Python source files are present."


def test_fresh_mixed_legacy_records_preserve_distinct_original_analyzers():
    result = integrate_production_truth({
        "commit_sha": SHA,
        "scanner_execution_records": [{
            "tool": "eslint", "status": "unavailable", "commit_sha": SHA,
            "verified_complete": False,
        }],
        "evidence_health_summary": {"records": [{
            "tool": "gitleaks", "status": "completed", "commit_sha": SHA,
            "verified_complete": True, "artifact_sha256": "b" * 64,
        }]},
    })
    rows = {r["scanner"]: r for r in result["analyzer_evidence_report"]["analyzers"]}
    assert rows["eslint"]["status"] == "unavailable"
    assert rows["gitleaks"]["status"] == "completed"
    assert rows["gitleaks"]["successful_passes"] == 1
    assert rows["bandit"]["status"] == "missing"
    assert result["analyzer_evidence_report"]["acceptance_ready"] is False


def test_old_projection_without_retained_raw_records_fails_closed_and_is_idempotent():
    from copy import deepcopy
    from nico.phase15_production_integration_v1 import integrate_production_truth
    payload = {
        "commit_sha": "a" * 40,
        "phase15_production_integration": {"version": "nico.phase15.production-integration.v2", "analyzer_contract_applied": True},
        "evidence_health_summary": {
            "scanner_records": [{"scanner": "eslint", "status": "capture_truncated", "successful_passes": 2}],
            "phase14_analyzer_evidence": {"required_scanners": ["eslint", "typescript"], "acceptance_ready": True},
        },
        "analyzer_evidence_report": {"acceptance_ready": True, "analyzers": [{"scanner": "eslint", "status": "capture_truncated"}]},
        "analyzer_evidence_ui": {"state": "ready"},
        "technical_score": 71, "evidence_adjusted_score": 67,
        "human_review_required": True, "client_delivery_allowed": False,
    }
    before = deepcopy(payload)
    result = integrate_production_truth(payload)
    marker = result["phase15_production_integration"]
    assert marker["regeneration_blocked"] is True
    assert marker["regeneration_blocker"] == "retained_analyzer_records_missing"
    report = result["analyzer_evidence_report"]
    assert report["acceptance_ready"] is False
    assert all(row["status"] == "missing" and row["run_count"] == 0 and row["successful_passes"] == 0 for row in report["analyzers"])
    assert "typescript" in [row["scanner"] for row in report["analyzers"]]
    assert result["analyzer_evidence_ui"]["state"] == "blocked"
    assert result["delivery_gate"]["analyzer_evidence_ready"] is False
    assert result["technical_score"] == 71 and result["evidence_adjusted_score"] == 67
    assert result["human_review_required"] is True and result["client_delivery_allowed"] is False
    assert "scanner_execution_records" not in result
    assert payload == before
    assert integrate_production_truth(result) == result


def test_old_projection_with_partial_retained_records_keeps_required_population():
    records = [
        {"scanner": name, "status": "completed", "commit_sha": SHA,
         "capture_complete": True, "artifact_sha256": digest * 64, "run_sequence": run}
        for name in ("bandit", "eslint", "gitleaks") for run, digest in [(1, "b"), (2, "c")]
    ]
    payload = {
        "commit_sha": SHA, "scanner_execution_records": records,
        "phase15_production_integration": {"version": "nico.phase15.production-integration.v2", "analyzer_contract_applied": True},
        "evidence_health_summary": {"phase14_analyzer_evidence": {"required_scanners": ["bandit", "eslint", "gitleaks", "typescript"]}},
    }
    result = integrate_production_truth(payload)
    report = result["analyzer_evidence_report"]
    typescript = next(row for row in report["analyzers"] if row["scanner"] == "typescript")
    assert typescript["status"] == "missing" and typescript["run_count"] == 0
    assert typescript["required"] is True and typescript["client_defect_allowed"] is False
    assert report["acceptance_ready"] is False
    assert result["delivery_gate"]["analyzer_evidence_ready"] is False
    assert result["scanner_execution_records"] == records
    assert all(row["consecutive_successful_passes"] == 2 for row in report["analyzers"] if row["scanner"] != "typescript")
    assert integrate_production_truth(result) == result
