from __future__ import annotations

from nico.comprehensive_scanner_stage_wording_v1 import scanner_stages


def _canonical() -> dict:
    return {
        "scanner_execution_records": [
            {
                "scanner_name": "gitleaks",
                "state": "completed_with_findings",
                "completed": True,
                "exact_commit_match": True,
                "artifact_hash": "a" * 64,
                "finding_count": 17,
                "findings": [],
            },
            {
                "scanner_name": "semgrep",
                "state": "completed_with_findings",
                "completed": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "finding_count": 581,
                "findings": [],
            },
        ],
        "assessment": {
            "canonical_scanner_finding_register": {
                "summary_by_scanner": {
                    "gitleaks": {
                        "raw": 17,
                        "material": 0,
                        "review_required": 16,
                        "approved_or_nonblocking": 1,
                        "excluded_test_only": 0,
                    },
                    "semgrep": {
                        "raw": 581,
                        "material": 0,
                        "review_required": 581,
                        "approved_or_nonblocking": 0,
                        "excluded_test_only": 0,
                    },
                },
                "totals": {
                    "raw": 598,
                    "material": 0,
                    "review_required": 597,
                    "approved_or_nonblocking": 1,
                    "excluded_test_only": 0,
                },
            }
        },
    }


def test_stage_separates_execution_completion_from_candidate_disposition() -> None:
    stage = scanner_stages(_canonical())[0]

    assert stage["status"] == "complete"
    assert "Scanner execution: 2/2 complete." in stage["summary"]
    assert "Candidate disposition: 597 pending human review from 598 raw candidates." in stage[
        "summary"
    ]
    assert "Confirmed material findings: 0." in stage["summary"]
    assert "Scanner completion does not equal candidate approval." in stage["summary"]


def test_scanner_evidence_uses_unambiguous_material_candidate_and_payload_terms() -> None:
    stage = scanner_stages(_canonical())[0]
    evidence = "\n".join(stage["evidence"])

    assert "gitleaks: execution=completed_with_findings" in evidence
    assert "confirmed material findings=0" in evidence
    assert "review-required candidates=16" in evidence
    assert "raw candidates=17" in evidence
    assert "raw candidate payload=count-only" in evidence
    assert "retained finding count" not in evidence
    assert "semgrep: execution=completed_with_findings" in evidence
    assert "review-required candidates=581" in evidence


def test_incomplete_scanner_remains_review_required() -> None:
    canonical = _canonical()
    canonical["scanner_execution_records"][1]["completed"] = False
    canonical["scanner_execution_records"][1]["state"] = "failed"
    canonical["scanner_execution_records"][1]["failure_reason"] = "Scanner failed."

    stage = scanner_stages(canonical)[0]

    assert stage["status"] == "review_required"
    assert "Scanner execution: 1/2 complete." in stage["summary"]
    assert stage["unavailable"] == ["semgrep: Scanner failed."]
