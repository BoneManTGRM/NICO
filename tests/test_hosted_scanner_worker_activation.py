from __future__ import annotations

from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts, extract_scanner_worker_artifact
from nico.hosted_scanner_worker import hosted_scanner_autorun_enabled


def _base_result() -> dict:
    return {
        "status": "complete",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 90,
                "status": "green",
                "summary": "Manifest-only dependency review.",
                "evidence": [],
                "findings": [],
                "unavailable": [
                    "pip-audit, npm audit, and OSV Scanner CLI execution are not yet run inside a sandboxed worker; hosted review uses manifest parsing plus OSV API where possible."
                ],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 86,
                "status": "green",
                "summary": "CI-backed static lift.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker in hosted mode."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 90,
                "status": "green",
                "summary": "Hosted secret review.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog."],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 90,
                "status": "green",
                "summary": "Velocity review.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Precise story-point expectation and deeper complexity analysis require a sandboxed worker."],
            },
        ],
        "findings": [],
    }


def _complete_artifact() -> dict:
    return {
        "worker_execution_state": "completed",
        "generated_at": "2026-07-08T00:00:00Z",
        "tools": {
            "pip-audit": {"status": "completed", "findings": []},
            "npm-audit": {"status": "completed", "findings": []},
            "osv-scanner": {"status": "completed", "findings": []},
            "bandit": {"status": "completed", "findings": []},
            "semgrep": {"status": "completed", "findings": []},
            "eslint": {"status": "completed", "findings": []},
            "typescript": {"status": "completed", "findings": []},
            "gitleaks": {"status": "completed", "findings": []},
            "trufflehog": {"status": "completed", "findings": []},
            "coverage": {"status": "completed", "findings": []},
        },
    }


def test_authorized_owner_repo_requests_enable_scanner_autorun(monkeypatch):
    monkeypatch.setenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "true")

    payload = {"repository": "BoneManTGRM/NICO", "authorized": True}

    assert hosted_scanner_autorun_enabled(payload) is True
    assert extract_scanner_worker_artifact(payload) == {"auto_run_scanner_worker": True}


def test_scanner_autorun_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "false")

    payload = {"repository": "BoneManTGRM/NICO", "authorized": True}

    assert hosted_scanner_autorun_enabled(payload) is False
    assert extract_scanner_worker_artifact(payload) is None


def test_complete_worker_artifact_lifts_dependency_and_removes_unavailable_notes():
    result = attach_scanner_worker_artifacts(_base_result(), {"scanner_worker_artifact": _complete_artifact()})

    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    secrets = next(item for item in result["sections"] if item["id"] == "secrets_review")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert result["scanner_worker_evidence_attached"] is True
    assert result["scanner_worker_artifact"]["dependency_evidence_complete"] is True
    assert dependency["score"] == 95
    assert dependency["unavailable"] == []
    assert static["unavailable"] == []
    assert secrets["unavailable"] == []
    assert any("coverage evidence" in item for item in velocity["evidence"])


def test_partial_auto_worker_artifact_keeps_missing_tools_unavailable():
    artifact = {
        "worker_execution_state": "completed",
        "tools": {
            "pip-audit": {"status": "completed", "findings": []},
            "bandit": {"status": "completed", "findings": []},
        },
    }

    result = attach_scanner_worker_artifacts(_base_result(), {"scanner_worker_artifact": artifact})
    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert result["scanner_worker_artifact"]["dependency_evidence_complete"] is False
    assert any("npm-audit" in item for item in dependency["unavailable"])
    assert any("semgrep" in item.lower() for item in static["unavailable"])
