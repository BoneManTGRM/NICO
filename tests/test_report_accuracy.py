from nico.report_accuracy import apply_report_accuracy, sanitize_client_note
from nico.reports import build_report_package


def test_raw_github_metadata_error_is_sanitized():
    note = 'Commit activity unavailable: GitHub returned 403: {"documentation_url":"https://docs.github.com/rest","message":"API rate limit exceeded"}'
    cleaned = sanitize_client_note(note)
    assert "documentation_url" not in cleaned
    assert "GitHub returned" not in cleaned
    assert "Commit metadata was unavailable" in cleaned


def test_required_sources_are_satisfied_by_available_evidence_even_when_stronger_tools_are_unavailable():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 86,
                "status": "green",
                "summary": "Built-in static analysis completed.",
                "evidence": ["Built-in static risk-pattern hits: 4.", "Repository files were inspected for static patterns."],
                "findings": [],
                "unavailable": ["Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker in hosted mode."],
            }
        ],
    }
    polished = apply_report_accuracy(result)
    section = polished["sections"][0]
    assert section["confidence"] == "medium"
    assert section["status"] == "green"
    assert section["score"] == 86
    assert section["missing_required_sources"] == []
    assert "static_analysis" in section["optional_unavailable_sources"]


def test_missing_required_evidence_still_blocks_green_status():
    result = {
        "status": "complete",
        "executive_summary": "Assessment.",
        "sections": [
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 92,
                "status": "green",
                "summary": "No useful evidence was returned.",
                "evidence": ["Repository files were inspected."],
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
    assert "secret_scanning" in section["missing_required_sources"]
    assert any("not equivalent to a complete scanner-clean result" in item for item in section["unverified_claims"])


def test_dependency_and_secret_review_can_remain_yellow_without_being_red_when_hosted_evidence_exists():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 72,
                "status": "yellow",
                "summary": "Hosted dependency evidence was reviewed.",
                "evidence": ["requirements.txt and package.json were inspected.", "Hosted OSV dependency intelligence returned broad-range warnings."],
                "findings": [],
                "unavailable": ["pip-audit and npm audit execution are not yet run inside a sandboxed worker."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 74,
                "status": "yellow",
                "summary": "Hosted secret pattern evidence was reviewed.",
                "evidence": ["Repository files were inspected.", "Secret-pattern classification: suspected=0, review-only=3, total=3."],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires gitleaks or trufflehog."],
            },
        ],
    }
    polished = apply_report_accuracy(result)
    sections = {item["id"]: item for item in polished["sections"]}
    assert sections["dependency_health"]["confidence"] == "medium"
    assert sections["dependency_health"]["score"] == 72
    assert sections["secrets_review"]["confidence"] == "medium"
    assert sections["secrets_review"]["score"] == 74
    assert polished["maturity_signal"]["score"] == 73


def test_security_audit_workflow_evidence_lifts_scanner_limited_sections():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 72,
                "status": "yellow",
                "summary": "Hosted dependency evidence was reviewed.",
                "evidence": ["requirements.txt and package.json were inspected."],
                "findings": [],
                "unavailable": ["pip-audit and npm audit execution are not yet run inside a sandboxed worker."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 74,
                "status": "yellow",
                "summary": "Hosted secret pattern evidence was reviewed.",
                "evidence": ["Repository files were inspected.", "Secret-pattern classification: suspected=0, review-only=3, total=3."],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires gitleaks or trufflehog."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 86,
                "status": "green",
                "summary": "Hosted static evidence was reviewed.",
                "evidence": ["Repository files were inspected for static patterns."],
                "findings": [],
                "unavailable": ["Semgrep and Bandit are not yet executed by a sandboxed worker."],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 95,
                "status": "green",
                "summary": "CI configured.",
                "evidence": ["GitHub Actions workflows found: .github/workflows/nico-ci.yml, .github/workflows/security-audit.yml."],
                "findings": [],
                "unavailable": [],
            },
        ],
    }
    polished = apply_report_accuracy(result)
    sections = {item["id"]: item for item in polished["sections"]}
    assert sections["dependency_health"]["score"] >= 80
    assert sections["dependency_health"]["status"] == "green"
    assert sections["dependency_health"]["confidence"] == "medium"
    assert sections["secrets_review"]["score"] >= 82
    assert sections["secrets_review"]["status"] == "green"
    assert sections["static_analysis"]["score"] >= 88
    assert polished["maturity_signal"]["score"] >= 81


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
