import pytest

from nico.phase14_analyzer_evidence_v1 import (
    AnalyzerEvidenceError,
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
    }


def test_classifies_timeout_capture_and_unsupported_separately():
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
    assert result["analyzers"][0]["consecutive_successful_passes"] == 2


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


def test_assessment_and_delivery_gate_receive_reconciled_evidence():
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
    assert result["delivery_gate"]["analyzer_evidence_ready"] is True
    assert len(result["delivery_gate"]["analyzer_evidence_manifest_sha256"]) == 64
