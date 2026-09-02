import pytest

from nico.phase14_analyzer_evidence_v1 import (
    AnalyzerEvidenceError,
    analyzer_report_projection,
    analyzer_ui_projection,
    apply_analyzer_evidence,
    classify_status,
    normalize_record,
    reconcile_analyzers,
)

SHA = "a" * 40
DIGEST_A = "b" * 64
DIGEST_B = "c" * 64
DIGEST_C = "d" * 64


def _success(scanner: str, digest: str, run: int):
    return {
        "scanner": scanner,
        "status": "completed",
        "commit_sha": SHA,
        "artifact_sha256": digest,
        "capture_complete": True,
        "run_sequence": run,
        "coverage": {"files": 10},
        "duration_seconds": 1.25,
    }


def test_classifies_alias_timeout_capture_and_unsupported_states():
    assert classify_status({"status": "passed"}) == "success"
    assert classify_status({"failure_cause": "worker timeout"}) == "timed_out"
    assert classify_status({"capture_complete": False}) == "capture_truncated"
    assert classify_status({"failure_cause": "unsupported language"}) == "unsupported_target"


def test_success_requires_exact_sha_hash_and_complete_capture():
    record = normalize_record(_success("bandit", DIGEST_A, 1), expected_sha=SHA)
    assert record["scanner"] == "bandit"
    assert record["artifact_sha256"] == DIGEST_A
    with pytest.raises(AnalyzerEvidenceError):
        normalize_record({**_success("bandit", DIGEST_A, 1), "capture_complete": False}, expected_sha=SHA)
    with pytest.raises(AnalyzerEvidenceError):
        normalize_record({**_success("bandit", DIGEST_A, 1), "commit_sha": "e" * 40}, expected_sha=SHA)


def test_not_applicable_requires_documented_scope_and_no_artifact():
    record = normalize_record(
        {
            "scanner": "eslint",
            "status": "not_applicable",
            "commit_sha": SHA,
            "run_sequence": 1,
            "scope_reason": "No JavaScript or TypeScript files are present.",
        },
        expected_sha=SHA,
    )
    assert record["status"] == "not_applicable"
    assert record["confirmed_client_defect"] is False
    assert "artifact_sha256" not in record
    with pytest.raises(AnalyzerEvidenceError):
        normalize_record(
            {"scanner": "eslint", "status": "not_applicable", "commit_sha": SHA},
            expected_sha=SHA,
        )


def test_failed_analyzer_cannot_become_confirmed_client_defect():
    record = normalize_record(
        {
            "scanner": "eslint",
            "status": "failed",
            "commit_sha": SHA,
            "confirmed_client_defect": True,
            "exit_code": 2,
        },
        expected_sha=SHA,
    )
    assert record["confirmed_client_defect"] is False


def test_two_consecutive_successful_exact_sha_passes_are_required():
    result = reconcile_analyzers(
        [_success("bandit", DIGEST_A, 1), _success("bandit", DIGEST_B, 2)],
        expected_sha=SHA,
        required_scanners=["bandit"],
    )
    assert result["acceptance_ready"] is True
    assert result["assurance_state"] == "decision_grade"
    assert result["analyzers"][0]["consecutive_successful_passes"] == 2
    assert result["analyzers"][0]["client_defect_allowed"] is True


def test_later_failure_breaks_consecutive_pass_sequence():
    records = [
        _success("bandit", DIGEST_A, 1),
        _success("bandit", DIGEST_B, 2),
        {"scanner": "bandit", "status": "failed", "commit_sha": SHA, "run_sequence": 3},
    ]
    result = reconcile_analyzers(records, expected_sha=SHA, required_scanners=["bandit"])
    analyzer = result["analyzers"][0]
    assert result["acceptance_ready"] is False
    assert analyzer["consecutive_successful_passes"] == 0
    assert analyzer["client_defect_allowed"] is False
    assert analyzer["failure_cause"]
    assert analyzer["assurance_impact"]
    assert analyzer["remediation"]
    assert result["blockers"][0]["scanner"] == "bandit"


def test_missing_required_scanner_blocks_acceptance_without_false_defect():
    result = reconcile_analyzers(
        [_success("bandit", DIGEST_A, 1), _success("bandit", DIGEST_B, 2)],
        expected_sha=SHA,
        required_scanners=["bandit", "gitleaks"],
    )
    missing = next(item for item in result["analyzers"] if item["scanner"] == "gitleaks")
    assert result["acceptance_ready"] is False
    assert missing["status"] == "missing"
    assert missing["client_defect_allowed"] is False


def test_single_success_has_actionable_repeatability_remediation():
    result = reconcile_analyzers(
        [_success("bandit", DIGEST_A, 1)],
        expected_sha=SHA,
        required_scanners=["bandit"],
    )
    analyzer = result["analyzers"][0]

    assert analyzer["failure_cause"].startswith("Only 1 of 2")
    assert "repeatability assurance" in analyzer["assurance_impact"]
    assert analyzer["remediation"] == "Retain 1 additional complete exact-SHA analyzer pass."
    assert result["blockers"][0]["remediation"] == analyzer["remediation"]


def test_invalid_record_is_retained_as_rejected_evidence_and_blocks_gate():
    result = reconcile_analyzers(
        [
            _success("bandit", DIGEST_A, 1),
            _success("bandit", DIGEST_B, 2),
            {"scanner": "eslint", "status": "completed", "commit_sha": "bad"},
        ],
        expected_sha=SHA,
        required_scanners=["bandit"],
    )
    assert result["acceptance_ready"] is False
    assert result["rejected_records"]
    assert "full commit SHA" in result["rejected_records"][0]["reason"]


def test_duplicate_records_do_not_inflate_pass_counts_or_manifest():
    records = [
        _success("bandit", DIGEST_A, 1),
        _success("bandit", DIGEST_A, 1),
        _success("bandit", DIGEST_B, 2),
    ]
    first = reconcile_analyzers(records, expected_sha=SHA, required_scanners=["bandit"])
    second = reconcile_analyzers(reversed(records), expected_sha=SHA, required_scanners=["bandit"])
    assert first["analyzers"][0]["run_count"] == 2
    assert first["evidence_manifest_sha256"] == second["evidence_manifest_sha256"]


def test_report_and_ui_projections_expose_state_impact_and_next_action():
    reconciliation = reconcile_analyzers([], expected_sha=SHA, required_scanners=["bandit"])
    report = analyzer_report_projection(reconciliation)
    ui = analyzer_ui_projection(reconciliation)
    assert report["assurance_state"] == "constrained"
    assert report["blockers"]
    assert "not itself a confirmed client defect" in report["disclaimer"]
    assert ui["state"] == "blocked"
    assert ui["rows"][0]["impact"]
    assert ui["rows"][0]["next_action"]


def test_assessment_report_ui_and_delivery_gate_receive_reconciled_evidence():
    records = []
    for scanner, digest in (("bandit", DIGEST_A), ("eslint", DIGEST_B), ("gitleaks", DIGEST_C)):
        records.extend([_success(scanner, digest, 1), _success(scanner, digest, 2)])
    result = apply_analyzer_evidence(
        {"evidence_health_summary": {"scanner_records": records}},
        expected_sha=SHA,
    )
    contract = result["evidence_health_summary"]["phase14_analyzer_evidence"]
    assert contract["acceptance_ready"] is True
    assert result["evidence_health_summary"]["incomplete_analyzers"] == []
    assert result["analyzer_evidence_report"]["ready_analyzers"] == 3
    assert result["analyzer_evidence_ui"]["state"] == "ready"
    assert result["delivery_gate"]["analyzer_evidence_ready"] is True
    assert result["delivery_gate"]["analyzer_evidence_blockers"] == []
    assert len(result["delivery_gate"]["analyzer_evidence_manifest_sha256"]) == 64
