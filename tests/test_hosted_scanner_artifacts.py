from __future__ import annotations

from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts, extract_scanner_worker_artifact


def _base_result() -> dict:
    return {
        "status": "complete",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 70,
                "status": "yellow",
                "summary": "Hosted pattern checks only.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker in hosted mode."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 92,
                "status": "green",
                "summary": "Hosted file scan only.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog."],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 73,
                "status": "yellow",
                "summary": "Hosted footprint estimate only.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Precise story-point expectation and deeper complexity analysis require a sandboxed worker."],
            },
        ],
        "findings": [],
    }


def _clean_worker_artifact(*, full_history: bool = True) -> dict:
    artifact = {
        "tools": {
            "bandit": {"status": "completed", "findings": []},
            "semgrep": {"status": "completed", "findings": []},
            "eslint": {"status": "completed", "findings": []},
            "typescript": {"status": "completed", "findings": []},
            "gitleaks": {"status": "completed", "findings": [], "scans_git_history": full_history},
            "trufflehog": {"status": "completed", "findings": [], "scans_git_history": full_history},
        }
    }
    if full_history:
        artifact["checkout"] = {
            "full_history_secret_scan_requested": True,
            "history_depth": "full",
            "commit_count": 42,
        }
        artifact["secret_history_scan"] = {
            "completed_tools": ["gitleaks", "trufflehog"],
            "history_aware": True,
        }
    return artifact


def test_extract_scanner_worker_artifact_accepts_aliases():
    artifact = {"tools": {}}

    assert extract_scanner_worker_artifact({"scanner_worker_artifact": artifact}) is artifact
    assert extract_scanner_worker_artifact({"worker_artifact": artifact}) is artifact
    assert extract_scanner_worker_artifact({}) is None


def test_missing_artifact_keeps_hosted_unavailable_notes():
    result = attach_scanner_worker_artifacts(_base_result(), {})

    assert result["scanner_worker_evidence_attached"] is False
    assert any("No scanner-worker artifact" in item for item in result["unavailable_data_notes"])
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    assert static["score"] == 70
    assert static["unavailable"]


def test_clean_complete_artifact_upgrades_static_secrets_and_velocity():
    result = attach_scanner_worker_artifacts(_base_result(), {"scanner_worker_artifact": _clean_worker_artifact()})

    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    secrets = next(item for item in result["sections"] if item["id"] == "secrets_review")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert result["scanner_worker_evidence_attached"] is True
    assert result["scanner_worker_artifact"]["static_evidence_complete"] is True
    assert result["scanner_worker_artifact"]["secret_evidence_complete"] is True
    assert static["score"] == 92
    assert static["status"] == "green"
    assert static["unavailable"] == []
    assert secrets["score"] == 95
    assert secrets["unavailable"] == []
    assert any("Full git-history secret scan executed" in item for item in secrets["evidence"])
    assert velocity["score"] == 82
    assert velocity["unavailable"] == []


def test_secret_tools_without_history_keep_history_gap_visible():
    result = attach_scanner_worker_artifacts(_base_result(), {"scanner_worker_artifact": _clean_worker_artifact(full_history=False)})

    secrets = next(item for item in result["sections"] if item["id"] == "secrets_review")

    assert secrets["score"] == 92
    assert any("Full git-history secret scan" in item for item in secrets["unavailable"])


def test_partial_artifact_keeps_missing_tools_unavailable():
    result = attach_scanner_worker_artifacts(
        _base_result(),
        {"scanner_worker_artifact": {"tools": {"bandit": {"status": "completed", "findings": []}}}},
    )

    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert result["scanner_worker_artifact"]["static_evidence_complete"] is False
    assert static["score"] == 70
    assert any("semgrep" in item.lower() for item in static["unavailable"])


def test_worker_findings_are_attached_to_matching_sections():
    result = attach_scanner_worker_artifacts(
        _base_result(),
        {
            "scanner_worker_artifact": {
                "checkout": {"full_history_secret_scan_requested": True, "history_depth": "full", "commit_count": 4},
                "secret_history_scan": {"completed_tools": ["gitleaks", "trufflehog"], "history_aware": True},
                "tools": {
                    "bandit": {"status": "completed", "findings": [{"severity": "low"}]},
                    "semgrep": {"status": "completed", "findings": []},
                    "eslint": {"status": "completed", "findings": []},
                    "typescript": {"status": "completed", "findings": []},
                    "gitleaks": {"status": "completed", "findings": [{"RuleID": "generic"}], "scans_git_history": True},
                    "trufflehog": {"status": "completed", "findings": [], "scans_git_history": True},
                },
            }
        },
    )

    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    secrets = next(item for item in result["sections"] if item["id"] == "secrets_review")

    assert any("static tools reported 1 finding" in item for item in static["findings"])
    assert any("secret tools reported 1 finding" in item for item in secrets["findings"])
    assert secrets["score"] < 92
