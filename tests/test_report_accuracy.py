from nico.report_accuracy import apply_report_accuracy, sanitize_client_note
from nico.reports import build_report_package


def test_raw_github_metadata_error_is_sanitized():
    note = 'Commit activity unavailable: GitHub returned 403: {"documentation_url":"https://docs.github.com/rest","message":"API rate limit exceeded"}'
    cleaned = sanitize_client_note(note)
    assert "documentation_url" not in cleaned
    assert "GitHub returned" not in cleaned
    assert "Commit metadata was unavailable" in cleaned


def test_missing_required_evidence_blocks_green_status():
    result = {
        "status": "complete",
        "executive_summary": "Assessment.",
        "sections": [
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 92,
                "status": "green",
                "summary": "Built-in pattern scan found no hits.",
                "evidence": ["Secret-pattern hits found in fetched text files: 0."],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog."],
            }
        ],
    }
    guarded = apply_report_accuracy(result)
    section = guarded["sections"][0]
    assert section["status"] == "yellow"
    assert section["score"] <= 74
    assert section["confidence"] == "limited"
    assert "secret_scanning" in section["unavailable_sources"]
    assert any("not equivalent to a complete scanner-clean result" in item for item in section["unverified_claims"])


def test_report_package_includes_verified_and_unverified_claims():
    package = build_report_package({
        "client_name": "Client",
        "project_name": "Project",
        "repository": "owner/repo",
        "sections": [
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 85,
                "status": "green",
                "summary": "CI present.",
                "evidence": ["GitHub Actions workflows found: .github/workflows/ci.yml."],
                "findings": [],
                "unavailable": ["Workflow run history unavailable: GitHub returned 429: {\"documentation_url\":\"x\"}"],
            }
        ],
    })
    report = package["formats"]["markdown"]
    assert "Verified / Unverified Claims" in report
    assert "documentation_url" not in report
    assert package["delivery_readiness"]["verdict"] == "human_review_required"
    assert package["formats"]["json"]["sections"][0]["confidence"] == "limited"
