from __future__ import annotations

from nico.comprehensive_scanner_completion_projection_v56 import (
    normalize_completed_scanner_retention,
)
from nico.v2_assessment_pipeline import build_canonical_assessment


def _canonical_record(*, completed: bool) -> dict[str, object]:
    status = "completed" if completed else "partial"
    scanner = {
        "scanner_name": "bandit",
        "status": status,
        "state": status,
        "completed": completed,
        "verified": completed,
        "exact_commit_match": True,
        "artifact_hash": "b" * 64 if completed else "",
        "raw_artifact_retention_complete": False,
        "verified_complete": False,
        "verified_for_this_report": False,
        "output_capture_complete": False,
        "verification_deficits": ["complete_artifact_capture_not_proven"],
        "findings": [],
        "exit_code": 1,
        "required": True,
    }
    return {
        "identity": {"commit_sha": "a" * 40},
        "scanner_execution_records": [scanner],
        "analyzer_evidence_report": {
            "analyzers": [
                {
                    "scanner": "bandit",
                    "status": "capture_truncated",
                    "remediation": "Persist the complete output.",
                    "failure_cause": "Analyzer output was not captured completely.",
                }
            ],
            "status_counts": {"capture_truncated": 1},
            "required_analyzers": 1,
            "disclaimer": (
                "Incomplete analyzer execution constrains assurance and is not "
                "itself a confirmed client defect."
            ),
        },
        "canonical_findings": [
            {
                "finding_id": "NICO-FINDING-ONE",
                "title": "Upgrade affected dependency",
                "category": "dependency",
                "finding_family": "dependency_vulnerability:ghsa-example",
                "priority": "P1",
            }
        ],
    }


def test_authoritative_completed_record_survives_v2_canonical_rebuild() -> None:
    normalized = normalize_completed_scanner_retention(
        _canonical_record(completed=True)
    )
    record = normalized["scanner_execution_records"][0]

    assert record["raw_artifact_retention_complete"] is True
    assert record["verified_complete"] is True
    assert record["verified_for_this_report"] is True
    assert record["output_capture_complete"] is True
    assert record["verification_deficits"] == []

    analyzer = normalized["analyzer_evidence_report"]["analyzers"][0]
    assert analyzer["status"] == "completed"
    assert analyzer["remediation"] is None
    assert analyzer["failure_cause"] is None
    assert normalized["analyzer_evidence_report"]["status_counts"] == {
        "completed": 1
    }
    assert normalized["analyzer_evidence_report"]["disclaimer"].startswith(
        "All applicable analyzers completed"
    )

    rebuilt = build_canonical_assessment(normalized)
    rebuilt_record = rebuilt["scanner_execution_records"][0]
    assert rebuilt_record["completed"] is True
    assert rebuilt_record["verified"] is True
    assert rebuilt_record["state"] == "completed"


def test_partial_record_is_not_promoted() -> None:
    normalized = normalize_completed_scanner_retention(
        _canonical_record(completed=False)
    )
    record = normalized["scanner_execution_records"][0]

    assert record["raw_artifact_retention_complete"] is False
    assert record["verified_complete"] is False
    assert record["verified_for_this_report"] is False
    assert record["output_capture_complete"] is False
    assert record["verification_deficits"] == [
        "complete_artifact_capture_not_proven"
    ]
    analyzer = normalized["analyzer_evidence_report"]["analyzers"][0]
    assert analyzer["status"] == "capture_truncated"
    assert analyzer["remediation"] == "Persist the complete output."

    rebuilt = build_canonical_assessment(normalized)
    rebuilt_record = rebuilt["scanner_execution_records"][0]
    assert rebuilt_record["completed"] is False
    assert rebuilt_record["verified"] is False
    assert rebuilt_record["state"] == "partial"
