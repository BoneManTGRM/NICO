from __future__ import annotations

from nico.scanner_artifact_scoring import _scanner_manifest_from_files
from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact


def test_completed_clean_counts_as_completed_tool_status() -> None:
    artifact = {
        "tools": {
            "typescript": {"status": "completed_clean", "finding_count": 0},
            "pip-audit": {"status": "completed", "finding_count": 0},
            "npm-audit": {"status": "completed", "finding_count": 0},
            "osv-scanner": {"status": "completed", "finding_count": 0},
            "bandit": {"status": "completed", "finding_count": 0},
            "semgrep": {"status": "completed", "finding_count": 0},
            "eslint": {"status": "completed", "finding_count": 0},
            "gitleaks": {"status": "completed", "finding_count": 0},
            "trufflehog": {"status": "completed", "finding_count": 0},
        }
    }

    normalized = normalize_scanner_worker_artifact(artifact)

    assert "typescript" in normalized["static_tools_completed"]
    assert normalized["missing_dependency_tools"] == []
    assert normalized["missing_static_tools"] == []
    assert normalized["missing_secret_tools"] == []


def test_scanner_manifest_from_github_artifacts_marks_required_tools() -> None:
    files = {
        "pip-audit.json": {"dependencies": []},
        "npm-audit.json": {"metadata": {"vulnerabilities": {"total": 0}}},
        "osv-scanner.json": {"results": []},
        "bandit.json": {"results": []},
        "semgrep.json": {"results": []},
        "eslint.json": [],
        "typescript-summary.json": {"status": "completed_clean", "finding_count": 0},
        "gitleaks-summary.json": {"status": "completed", "finding_count": 0},
        "trufflehog-summary.json": {"status": "completed", "finding_count": 0},
    }
    artifacts = {"security-audit-evidence": {"run_id": 123, "created_at": "2026-07-10T00:00:00Z", "files": files}}

    manifest = _scanner_manifest_from_files(files, artifacts, "BoneManTGRM/NICO")
    normalized = normalize_scanner_worker_artifact(manifest)

    assert manifest["worker_execution_state"] == "completed"
    assert normalized["dependency_evidence_complete"] is True
    assert normalized["static_evidence_complete"] is True
    assert normalized["secret_evidence_complete"] is True
    assert normalized["dependency_finding_count"] == 0
    assert normalized["static_finding_count"] == 0
    assert normalized["secret_finding_count"] == 0
