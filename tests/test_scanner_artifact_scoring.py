from nico.scanner_artifact_scoring import apply_scanner_artifact_scoring, scanner_artifact_access_status
import nico.scanner_artifact_scoring as scanner


def _sections():
    return [
        {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 77, "status": "green", "evidence": [], "findings": [], "unavailable": []},
        {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 74, "status": "yellow", "evidence": [], "findings": [], "unavailable": []},
        {"id": "static_analysis", "label": "Static Analysis", "score": 86, "status": "green", "evidence": [], "findings": [], "unavailable": []},
        {"id": "ci_cd", "label": "CI/CD Analysis", "score": 82, "status": "green", "evidence": [], "findings": [], "unavailable": []},
    ]


def test_scanner_artifact_status_reports_missing_token(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    status = scanner_artifact_access_status("BoneManTGRM/NICO")
    assert status["status"] == "token_missing"
    assert status["token_configured"] is False
    assert "NICO_GITHUB_TOKEN" in status["message"]


def test_scanner_artifact_status_reports_missing_repo(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    status = scanner_artifact_access_status("")
    assert status["status"] == "repo_unavailable"
    assert status["repository"] == "unavailable"


def test_scanner_artifact_scoring_adds_visible_unavailable_note_when_token_missing(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = {"repository": "BoneManTGRM/NICO", "sections": _sections()}
    scored = apply_scanner_artifact_scoring(result)
    assert scored["scanner_artifact_summary"]["status"] == "artifact_access_unavailable"
    assert scored["scanner_artifact_summary"]["access"]["status"] == "token_missing"
    for section in scored["sections"]:
        assert any("GitHub Actions artifact access unavailable" in note for note in section.get("unavailable", []))


def test_scanner_artifact_scoring_does_not_mutate_input_when_access_missing(monkeypatch):
    monkeypatch.delenv("NICO_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = {"repository": "BoneManTGRM/NICO", "sections": _sections()}
    scored = apply_scanner_artifact_scoring(result)
    assert scored is not result
    assert result["sections"][0]["unavailable"] == []


def test_clean_gitleaks_and_credential_artifacts_lift_secret_review(monkeypatch):
    monkeypatch.setattr(scanner, "scanner_artifact_access_status", lambda repo: {"status": "ok", "repository": repo, "token_configured": True})
    monkeypatch.setattr(
        scanner,
        "_fetch_recent_artifacts",
        lambda repo: {
            "security-audit-evidence": {
                "workflow": "Security Audit Evidence",
                "conclusion": "success",
                "files": {
                    "credential-scan.json": {"findings": []},
                    "gitleaks.json": [],
                },
            }
        },
    )
    scored = apply_scanner_artifact_scoring({"repository": "BoneManTGRM/NICO", "sections": _sections()})
    secret = next(section for section in scored["sections"] if section["id"] == "secrets_review")
    assert secret["status"] == "green"
    assert secret["score"] >= 93
    assert any("gitleaks git-history" in item for item in secret["evidence"])
    assert "gitleaks.json" in scored["scanner_artifact_summary"]["files"]


def test_clean_gitleaks_summary_lifts_secret_review_after_generic_false_positive(monkeypatch):
    monkeypatch.setattr(scanner, "scanner_artifact_access_status", lambda repo: {"status": "ok", "repository": repo, "token_configured": True})
    monkeypatch.setattr(
        scanner,
        "_fetch_recent_artifacts",
        lambda repo: {
            "security-audit-evidence": {
                "workflow": "Security Audit Evidence",
                "conclusion": "success",
                "files": {
                    "credential-scan.json": {"findings": []},
                    "gitleaks-summary.json": {"scanner": "gitleaks", "finding_count": 0, "artifact_present": True},
                },
            }
        },
    )
    sections = _sections()
    secret = next(section for section in sections if section["id"] == "secrets_review")
    secret["score"] = 55
    secret["findings"] = ["Potential secret exposure requires immediate human review and credential rotation if confirmed."]
    secret["evidence"] = [
        "Secret-pattern hits found in fetched text files: 7.",
        "nico/api/main.py:192: potential generic_secret_assignment evidence toke...oken",
    ]
    scored = apply_scanner_artifact_scoring({"repository": "BoneManTGRM/NICO", "sections": sections})
    secret = next(section for section in scored["sections"] if section["id"] == "secrets_review")
    assert secret["status"] == "green"
    assert secret["score"] >= 93
    assert not secret["findings"]
    assert any("false-positive source-code signals" in item for item in secret["evidence"])


def test_clean_dependency_artifacts_lift_after_manifest_only_findings(monkeypatch):
    monkeypatch.setattr(scanner, "scanner_artifact_access_status", lambda repo: {"status": "ok", "repository": repo, "token_configured": True})
    monkeypatch.setattr(
        scanner,
        "_fetch_recent_artifacts",
        lambda repo: {
            "security-audit-evidence": {
                "workflow": "Security Audit Evidence",
                "conclusion": "success",
                "files": {
                    "pip-audit.json": {"dependencies": []},
                    "npm-audit.json": {"metadata": {"vulnerabilities": {"total": 0}}},
                },
            }
        },
    )
    sections = _sections()
    deps = next(section for section in sections if section["id"] == "dependency_health")
    deps["score"] = 46
    deps["status"] = "yellow"
    deps["findings"] = ["package.json exists but no JavaScript lockfile was found in the checked paths."]
    scored = apply_scanner_artifact_scoring({"repository": "BoneManTGRM/NICO", "sections": sections})
    deps = next(section for section in scored["sections"] if section["id"] == "dependency_health")
    assert deps["status"] == "green"
    assert deps["score"] >= 90
    assert not deps["findings"]


def test_gitleaks_findings_keep_secret_review_yellow(monkeypatch):
    monkeypatch.setattr(scanner, "scanner_artifact_access_status", lambda repo: {"status": "ok", "repository": repo, "token_configured": True})
    monkeypatch.setattr(
        scanner,
        "_fetch_recent_artifacts",
        lambda repo: {
            "security-audit-evidence": {
                "workflow": "Security Audit Evidence",
                "conclusion": "success",
                "files": {
                    "credential-scan.json": {"findings": []},
                    "gitleaks.json": [{"RuleID": "generic-api-key", "File": "example.txt"}],
                },
            }
        },
    )
    scored = apply_scanner_artifact_scoring({"repository": "BoneManTGRM/NICO", "sections": _sections()})
    secret = next(section for section in scored["sections"] if section["id"] == "secrets_review")
    assert secret["status"] == "yellow"
    assert secret["score"] <= 60
    assert any("gitleaks artifact reported 1" in item for item in secret["findings"])
