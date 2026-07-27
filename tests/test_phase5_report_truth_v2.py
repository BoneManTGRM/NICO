from __future__ import annotations

from nico.phase5_report_truth_v2 import install_phase5_report_truth_v2, reconcile_phase5_report_truth


TARGET = "a" * 40


def test_v2_accepts_complete_status_only_when_proof_fields_are_retained() -> None:
    install_phase5_report_truth_v2()
    assessment = {
        "sections": [
            {"id": "static_analysis", "label": "Static", "score": 79, "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency", "score": 92, "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets", "score": 93, "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings_register": [],
    }
    bandit = {
        "tool": "bandit",
        "status": "complete",
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
    stages = {
        "deep_scanner_triage": {
            "nested": {
                "scanner_artifact": {
                    "target_commit_sha": TARGET,
                    "tools": {"bandit": bandit},
                }
            }
        }
    }

    result = reconcile_phase5_report_truth(assessment, stages)
    record = result["evidence_health_summary"]["scanner_records"]["bandit"]

    assert record["status"] == "completed"
    assert record["execution_complete"] is True
    assert record["target_commit_sha"] == TARGET
    assert "bandit" in result["evidence_health_summary"]["completed_scanners"]


def test_v2_does_not_upgrade_legacy_complete_without_proof_fields() -> None:
    install_phase5_report_truth_v2()
    assessment = {
        "sections": [
            {"id": "static_analysis", "label": "Static", "score": 79, "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings_register": [],
    }
    stages = {
        "deep_scanner_triage": {
            "target_commit_sha": TARGET,
            "scanner_results": [{"tool": "bandit", "status": "complete", "findings": []}],
        }
    }

    result = reconcile_phase5_report_truth(assessment, stages)
    record = result["evidence_health_summary"]["scanner_records"]["bandit"]

    assert record["status"] == "completed"
    assert record["execution_complete"] is False
    assert "bandit" not in result["evidence_health_summary"]["completed_scanners"]
