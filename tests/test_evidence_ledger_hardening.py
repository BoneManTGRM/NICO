from __future__ import annotations

import json

from nico.evidence_artifact_bundle import attach_evidence_artifact_bundle, build_evidence_artifact_bundle, build_hardened_evidence_ledger


def result_with_evidence() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T21:30:00Z",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency/Library Ecosystem",
                "score": 95,
                "status": "green",
                "evidence": ["pip-audit completed with zero findings."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 74,
                "status": "yellow",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full git-history secret scan did not provide verified history coverage."],
            },
        ],
        "scanner_worker_artifact": {
            "tools": {
                "pip-audit": {"status": "completed", "completed": True, "finding_count": 0, "verified_for_this_report": True, "current_run": True},
                "gitleaks": {"status": "unavailable", "completed": False, "finding_count": 0, "verified_for_this_report": False, "current_run": True},
            }
        },
        "complexity_engine_summary": {"status": "completed", "verified_for_this_report": True, "current_run": True, "complexity_score": 88},
        "reports": {"markdown": "# Report\n", "html": "<html></html>"},
        "human_review_required": True,
    }


def test_hardened_evidence_ledger_classifies_section_and_tool_rows():
    ledger = build_hardened_evidence_ledger(result_with_evidence())

    assert ledger["artifact_schema"] == "nico.evidence_ledger.v1"
    assert ledger["entry_count"] >= 5
    assert ledger["verified_entry_count"] >= 2
    assert ledger["unavailable_entry_count"] >= 1
    assert ledger["human_review_required"] is True
    assert ledger["ledger_hash"]
    assert any(item["entry_type"] == "scanner_tool" and item["scope"] == "pip-audit" for item in ledger["entries"])
    assert any(item["entry_type"] == "section" and item["verification_state"] == "unavailable" for item in ledger["entries"])


def test_evidence_bundle_exports_ledger_artifact_and_hash():
    bundle = build_evidence_artifact_bundle(result_with_evidence())

    assert bundle["artifacts"]["evidence_ledger_json"]["available"] is True
    assert bundle["artifacts"]["evidence_ledger_json"]["sha256"]
    assert bundle["evidence_ledger"]["ledger_hash"]
    assert bundle["evidence_ledger"]["unavailable_entry_count"] >= 1


def test_attach_evidence_bundle_adds_ledger_report_export():
    output = attach_evidence_artifact_bundle(result_with_evidence())

    assert output["evidence_ledger"]["artifact_schema"] == "nico.evidence_ledger.v1"
    assert output["reports"]["evidence_ledger_filename"].endswith(".json")
    parsed = json.loads(output["reports"]["evidence_ledger_json"])
    assert parsed["repository"] == "BoneManTGRM/NICO"
