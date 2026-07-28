from __future__ import annotations

from nico.phase5_report_truth_v2 import install_phase5_report_truth_v2, reconcile_phase5_report_truth


TARGET = "a" * 40


def _assessment() -> dict:
    return {
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static",
                "score": 79,
                "evidence": [],
                "findings": ["Failed static tools: bandit"],
                "unavailable": ["bandit evidence unavailable"],
            },
            {"id": "dependency_health", "label": "Dependency", "score": 92, "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets", "score": 93, "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings_register": [],
    }


def _complete_bandit() -> dict:
    return {
        "tool": "bandit",
        "status": "complete",
        "category": "static",
        "verified_for_this_report": True,
        "output_capture_complete": True,
        "raw_artifact_capture_complete": True,
        "returncode_valid": True,
        "timed_out": False,
        "artifact_hash": "artifact",
        "raw_artifact_sha256": "raw",
        "deterministic_fingerprint": "fingerprint",
        "findings": [],
    }


def test_v2_accepts_complete_status_only_when_proof_fields_are_retained() -> None:
    install = install_phase5_report_truth_v2()
    stages = {
        "deep_scanner_triage": {
            "nested": {
                "scanner_artifact": {
                    "target_commit_sha": TARGET,
                    "tools": {"bandit": _complete_bandit()},
                }
            }
        }
    }

    result = reconcile_phase5_report_truth(_assessment(), stages)
    record = result["evidence_health_summary"]["scanner_records"]["bandit"]
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert install["stale_scanner_failure_text_removed_only_after_proof"] is True
    assert record["status"] == "completed"
    assert record["execution_complete"] is True
    assert record["target_commit_sha"] == TARGET
    assert "bandit" in result["evidence_health_summary"]["completed_scanners"]
    assert static["findings"] == []
    assert static["unavailable"] == []
    assert static["scanner_execution_status"] == "complete_exact_sha"


def test_v2_propagates_plain_stage_commit_to_nested_tool_record() -> None:
    install = install_phase5_report_truth_v2()
    stages = {
        "deep_scanner_triage": {
            "commit_sha": TARGET,
            "scanner_artifact": {"tools": {"bandit": _complete_bandit()}},
        }
    }

    result = reconcile_phase5_report_truth(_assessment(), stages)
    record = result["evidence_health_summary"]["scanner_records"]["bandit"]

    assert install["plain_stage_commit_propagation"] is True
    assert record["target_commit_sha"] == TARGET
    assert record["exact_commit_match"] is True
    assert record["execution_complete"] is True


def test_v2_does_not_upgrade_legacy_complete_without_proof_fields() -> None:
    install_phase5_report_truth_v2()
    stages = {
        "deep_scanner_triage": {
            "target_commit_sha": TARGET,
            "scanner_results": [{"tool": "bandit", "status": "complete", "category": "static", "findings": []}],
        }
    }

    result = reconcile_phase5_report_truth(_assessment(), stages)
    record = result["evidence_health_summary"]["scanner_records"]["bandit"]
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert record["status"] == "completed"
    assert record["execution_complete"] is False
    assert "bandit" not in result["evidence_health_summary"]["completed_scanners"]
    assert "Failed static tools: bandit" in static["findings"]
    assert static["unavailable"] == [
        "bandit exact-SHA evidence remains completed: completion requirements were not met"
    ]


def test_v2_missing_scanner_record_is_not_reported_as_an_improvement() -> None:
    install = install_phase5_report_truth_v2()
    result = reconcile_phase5_report_truth(
        _assessment(),
        {"evidence_reconciliation_and_scoring": {"commit_sha": TARGET}},
    )
    outcomes = result["phase5_verified_outcomes"]

    assert install["missing_scanner_records_are_not_changes"] is True
    assert outcomes["scanner_status_changes"] == {}
    assert set(outcomes["unobserved_baseline_scanners"]) == {
        "bandit",
        "eslint",
        "gitleaks",
        "osv-scanner",
    }
    assert outcomes["missing_scanner_records_count_as_changes"] is False
