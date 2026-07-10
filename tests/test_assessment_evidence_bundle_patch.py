from __future__ import annotations

import json

from nico.assessment_evidence_bundle_patch import (
    attach_assessment_evidence_bundle,
    build_assessment_evidence_bundle,
    install_assessment_evidence_bundle_patch,
)
from nico.evidence_artifact_bundle import attach_evidence_artifact_bundle


def sample_result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-10T00:00:00Z",
        "assessment_mode": "express",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 74,
                "status": "yellow",
                "evidence": ["pip-audit completed."],
                "findings": [],
                "unavailable": ["osv-scanner unavailable."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 74,
                "status": "yellow",
                "evidence": [],
                "findings": ["Bandit reported findings."],
                "unavailable": [],
            },
        ],
        "scanner_worker_artifact": {
            "run_id": "worker-run-1",
            "worker_execution_state": "completed",
            "artifact_hash": "worker-hash",
            "orchestration": {
                "run_id": "worker-run-1",
                "manifest_hash": "manifest-hash",
                "completed_tools": ["pip-audit", "bandit"],
                "unavailable_tools": ["osv-scanner"],
                "finding_tools": ["bandit"],
                "tools": [
                    {
                        "run_id": "worker-run-1",
                        "tool": "pip-audit",
                        "category": "dependency",
                        "status": "completed",
                        "exit_code": 0,
                        "timed_out": False,
                        "finding_count": 0,
                        "artifact_hash": "pip-hash",
                    },
                    {
                        "run_id": "worker-run-1",
                        "tool": "bandit",
                        "category": "static",
                        "status": "completed",
                        "exit_code": 1,
                        "timed_out": False,
                        "finding_count": 2,
                        "has_findings": True,
                        "artifact_hash": "bandit-hash",
                    },
                    {
                        "run_id": "worker-run-1",
                        "tool": "osv-scanner",
                        "category": "dependency",
                        "status": "unavailable",
                        "exit_code": None,
                        "timed_out": False,
                        "finding_count": 0,
                        "reason": "not installed",
                    },
                ],
            },
            "tools": {},
        },
        "complexity_engine_summary": {"status": "completed", "hotspot_count": 0},
        "secret_history_scan": {"history_aware": True, "completed_tools": ["gitleaks"]},
        "evidence_ledger": {"entry_count": 3, "ledger_hash": "ledger-hash"},
        "reports": {"markdown": "# Report", "html": "<html></html>"},
        "human_review_required": True,
    }


def test_build_assessment_evidence_bundle_normalizes_scanner_artifacts() -> None:
    result = sample_result()
    bundle = build_assessment_evidence_bundle(result, {"bundle_hash": "source-hash", "ci_references": ["workflow run 1"]})

    assert bundle["artifact_schema"] == "nico.assessment_evidence_bundle.v1"
    assert bundle["assessment_id"]
    assert bundle["repository"] == "BoneManTGRM/NICO"
    assert bundle["scanner_worker"]["run_id"] == "worker-run-1"
    assert bundle["scanner_worker"]["artifact_hash"] == "worker-hash"
    assert bundle["scanner_worker"]["orchestration_hash"] == "manifest-hash"
    assert bundle["tool_groups"]["dependency"] == ["pip-audit", "osv-scanner"]
    assert bundle["tool_groups"]["static"] == ["bandit"]
    assert "bandit" in bundle["scanner_worker"]["finding_tools"]
    assert bundle["complexity"]["summary_attached"] is True
    assert bundle["secrets"]["history_aware"] is True
    assert bundle["ci"]["references"] == ["workflow run 1"]
    assert bundle["evidence_ledger"]["ledger_hash"] == "ledger-hash"
    assert bundle["bundle_hash"]


def test_attach_assessment_evidence_bundle_adds_report_export() -> None:
    result = sample_result()
    result["evidence_artifact_bundle"] = {"bundle_hash": "source-hash", "artifacts": {}, "ci_references": []}

    output = attach_assessment_evidence_bundle(result)

    assert output["assessment_evidence_bundle"]["artifact_schema"] == "nico.assessment_evidence_bundle.v1"
    assert output["evidence_artifact_bundle"]["assessment_evidence_bundle"]["repository"] == "BoneManTGRM/NICO"
    assert output["evidence_artifact_bundle"]["artifacts"]["assessment_evidence_bundle_json"]["available"] is True
    parsed = json.loads(output["reports"]["assessment_evidence_bundle_json"])
    assert parsed["scanner_worker"]["run_id"] == "worker-run-1"
    assert output["reports"]["assessment_evidence_bundle_filename"].endswith(".json")


def test_installed_patch_extends_existing_evidence_bundle_export() -> None:
    install_assessment_evidence_bundle_patch()
    output = attach_evidence_artifact_bundle(sample_result())

    assert output["assessment_evidence_bundle"]["artifact_schema"] == "nico.assessment_evidence_bundle.v1"
    assert output["evidence_artifact_bundle"]["assessment_evidence_bundle"]["repository"] == "BoneManTGRM/NICO"
    assert "assessment_evidence_bundle_json" in output["reports"]
    assert "assessment_evidence_bundle_json" in output["evidence_artifact_bundle"]["artifacts"]
