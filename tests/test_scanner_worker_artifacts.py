from nico.scanner_worker_artifacts import (
    normalize_scanner_worker_artifact,
    scanner_worker_evidence_notes,
)


def test_scanner_worker_artifact_keeps_missing_tools_unavailable():
    artifact = normalize_scanner_worker_artifact({"tools": {"bandit": {"status": "completed", "findings": []}}})

    assert artifact["static_tools_completed"] == ["bandit"]
    assert artifact["static_evidence_complete"] is False
    assert "semgrep" in artifact["missing_static_tools"]
    assert "gitleaks" in artifact["missing_secret_tools"]


def test_scanner_worker_artifact_counts_bandit_findings():
    artifact = normalize_scanner_worker_artifact(
        {
            "tools": {
                "bandit": {"status": "completed", "findings": [{"severity": "low"}] * 47},
                "semgrep": {"status": "completed", "findings": []},
                "eslint": {"status": "completed", "findings": []},
                "typescript": {"status": "completed", "findings": []},
                "gitleaks": {"status": "completed", "findings": []},
                "trufflehog": {"status": "completed", "findings": []},
            }
        }
    )

    assert artifact["static_evidence_complete"] is True
    assert artifact["secret_evidence_complete"] is True
    assert artifact["static_finding_count"] == 47
    assert artifact["tools"]["bandit"]["severity_counts"] == {"low": 47}


def test_scanner_worker_evidence_notes_are_report_ready():
    notes = scanner_worker_evidence_notes(
        {
            "tools": [
                {"tool": "bandit", "status": "completed", "findings": []},
                {"tool": "gitleaks", "status": "completed", "findings": []},
            ]
        }
    )

    assert "Scanner-worker static tools completed: bandit." in notes["evidence"]
    assert "Scanner-worker secret tools completed: gitleaks." in notes["evidence"]
    assert any("semgrep" in item for item in notes["unavailable"])
    assert any("trufflehog" in item for item in notes["unavailable"])
