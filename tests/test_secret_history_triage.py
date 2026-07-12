from __future__ import annotations

import nico.secret_history_triage as triage


def test_unverified_test_fixture_is_disclosed_but_not_material() -> None:
    findings = triage.classify_history_findings(
        [
            {
                "tool": "gitleaks",
                "rule_id": "generic-api-key",
                "path": "tests/test_scanner_tool_runners.py",
                "line": 20,
                "verified": False,
            }
        ]
    )

    assert findings[0]["test_only"] is True
    assert findings[0]["material"] is False
    assert findings[0]["review_required"] is False
    assert findings[0]["disposition"] == "test-only"


def test_verified_finding_remains_material_even_in_test_path() -> None:
    findings = triage.classify_history_findings(
        [
            {
                "tool": "trufflehog",
                "rule_id": "Postgres",
                "path": "tests/test_persistent_storage.py",
                "line": 60,
                "verified": True,
            }
        ]
    )

    assert findings[0]["test_only"] is True
    assert findings[0]["material"] is True
    assert findings[0]["review_required"] is False


def test_unverified_production_candidate_remains_material_review_item() -> None:
    findings = triage.classify_history_findings(
        [
            {
                "tool": "trufflehog",
                "rule_id": "Postgres",
                "path": "nico/storage.py",
                "line": 100,
                "verified": False,
            }
        ]
    )

    assert findings[0]["test_only"] is False
    assert findings[0]["material"] is True
    assert findings[0]["review_required"] is True


def test_section_reports_full_history_completion_and_excluded_test_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        triage,
        "_SECRETS_SECTION_DELEGATE",
        lambda _repo, _scanner: {
            "id": "secrets_review",
            "label": "Secrets Exposure Review",
            "score": 95,
            "status": "green",
            "evidence": ["Both full-history scanners completed."],
            "verified_claims": ["Both full-history scanners completed."],
            "findings": [],
            "unavailable": [],
        },
    )
    scanner = {
        "scanner_results": [
            {
                "scanner": "gitleaks",
                "execution_completed": True,
                "full_history_covered": True,
                "total_finding_count": 3,
                "material_finding_count": 0,
                "review_finding_count": 0,
                "excluded_test_finding_count": 3,
                "verified_finding_count": 0,
            },
            {
                "scanner": "trufflehog",
                "execution_completed": True,
                "full_history_covered": True,
                "total_finding_count": 6,
                "material_finding_count": 0,
                "review_finding_count": 0,
                "excluded_test_finding_count": 6,
                "verified_finding_count": 0,
            },
        ]
    }

    section = triage.secret_history_section_with_test_triage({}, scanner)

    assert section["secret_history_triage"]["history_scanners_completed"] == 2
    assert section["secret_history_triage"]["material_finding_count"] == 0
    assert section["secret_history_triage"]["excluded_test_finding_count"] == 9
    assert any("excluded test-only=9" in item for item in section["evidence"])
