from __future__ import annotations

import base64
import json

from nico.evidence_artifact_bundle import attach_evidence_artifact_bundle, build_evidence_artifact_bundle
from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts


def _result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T00:00:00Z",
        "assessment_mode": "express",
        "timeframe_days": 180,
        "repository_metadata": {"default_branch": "main"},
        "maturity_signal": {"level": "Senior", "score": 90},
        "maturity_semaphore": {"CI/CD Analysis": "green"},
        "sections": [
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 95,
                "status": "green",
                "summary": "CI review.",
                "evidence": ["GitHub Actions workflow runs returned in assessment window: 10; success=9; non-success=1."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 90,
                "status": "green",
                "summary": "Secret review.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full git-history secret scan did not provide verified history coverage."],
            },
        ],
        "findings": [],
        "repairs": ["Review evidence."],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {
            "markdown": "# Report\n",
            "html": "<html>Report</html>",
            "pdf_base64": base64.b64encode(b"pdf-bytes").decode("ascii"),
            "pdf_filename": "report.pdf",
        },
        "scanner_worker_artifact": {"static_evidence_complete": True},
        "complexity_engine": {"complexity_score": 88},
        "bandit_triage": {"finding_count": 0},
        "secret_history_scan": {"history_aware": True},
        "human_review_required": True,
        "safety_boundary": "Authorized defensive assessment only.",
    }


def test_build_evidence_artifact_bundle_includes_hashes_and_inventory():
    bundle = build_evidence_artifact_bundle(_result())

    assert bundle["artifact_schema"] == "nico.evidence_bundle.v1"
    assert bundle["bundle_hash"]
    assert bundle["artifacts"]["markdown"]["sha256"]
    assert bundle["artifacts"]["html"]["sha256"]
    assert bundle["artifacts"]["pdf"]["available"] is True
    assert bundle["artifacts"]["raw_evidence_json"]["sha256"]
    assert bundle["raw_evidence_json"]["repository"] == "BoneManTGRM/NICO"
    assert bundle["scanner_outputs"]["complexity_engine"]["complexity_score"] == 88
    assert bundle["ci_references"]
    assert bundle["unavailable_inventory"][0]["scope"] == "Secrets Exposure Review"


def test_attach_evidence_artifact_bundle_adds_report_json_export():
    result = attach_evidence_artifact_bundle(_result())

    assert result["evidence_artifact_bundle"]["artifact_schema"] == "nico.evidence_bundle.v1"
    assert result["reports"]["evidence_bundle_filename"].endswith(".json")
    parsed = json.loads(result["reports"]["evidence_bundle_json"])
    assert parsed["repository"] == "BoneManTGRM/NICO"


def test_scanner_artifact_attachment_keeps_existing_behavior_before_bundle():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T00:00:00Z",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 86,
                "status": "green",
                "summary": "Static review.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Semgrep and Bandit unavailable."],
            }
        ],
        "findings": [],
        "reports": {"markdown": "# Report\n", "html": "<html></html>"},
        "human_review_required": True,
    }
    artifact = {
        "tools": {
            "bandit": {"status": "completed", "findings": []},
            "semgrep": {"status": "completed", "findings": []},
            "eslint": {"status": "completed", "findings": []},
            "typescript": {"status": "completed", "findings": []},
        }
    }

    updated = attach_scanner_worker_artifacts(result, {"scanner_worker_artifact": artifact})

    assert updated["scanner_worker_evidence_attached"] is True
    assert "evidence_artifact_bundle" not in updated
