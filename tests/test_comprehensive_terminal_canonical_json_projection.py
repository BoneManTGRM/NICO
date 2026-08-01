from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_api_controller import _project_report


def _canonical_json() -> dict[str, object]:
    return {
        "artifact_schema": "nico.comprehensive.canonical-report.v1",
        "canonical_truth_sha256": "a" * 64,
        "identity": {
            "run_id": "comprun_projection_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
        },
        "assessment": {
            "technical_score": 71,
            "canonical_evidence_adjusted_score": 61,
            "maturity_signal": {
                "level": "Mid",
                "presented_score": 71,
                "technical_score": 71,
                "canonical_evidence_adjusted_score": 61,
            },
            "sections": [
                {
                    "id": "dependencies",
                    "label": "Dependency / Library Analysis",
                    "presented_score": 22,
                    "presented_status": "CRITICAL",
                }
            ],
            "scanner_execution_records": [
                {
                    "scanner_name": "osv-scanner",
                    "status": "completed",
                    "completed": True,
                    "verified_complete": True,
                    "findings": [],
                }
            ],
        },
    }


def test_terminal_report_projection_retains_complete_canonical_json_artifact() -> None:
    canonical = _canonical_json()
    report = {
        "service_id": "comprehensive",
        "report_id": "report_projection_001",
        "canonical_truth_sha256": "a" * 64,
        "markdown": "# NICO Comprehensive Technical Assessment",
        "html": "<!doctype html><html></html>",
        "pdf_base64": "JVBERi0xLjQK",
        "json": canonical,
    }

    projected = _project_report(report)

    assert projected["json"] == canonical
    assert projected["json"] is not canonical
    assert projected["json"]["identity"]["run_id"] == "comprun_projection_001"
    assert projected["json"]["assessment"]["technical_score"] == 71
    assert projected["json"]["assessment"]["sections"][0]["presented_score"] == 22
    assert projected["json"]["assessment"]["scanner_execution_records"][0]["scanner_name"] == "osv-scanner"


def test_terminal_report_projection_does_not_mutate_persisted_canonical_artifact() -> None:
    canonical = _canonical_json()
    persisted = deepcopy(canonical)

    projected = _project_report({"json": canonical})
    projected["json"]["assessment"]["technical_score"] = 99

    assert canonical == persisted
