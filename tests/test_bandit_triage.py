from __future__ import annotations

from nico.bandit_triage import build_bandit_triage, classify_bandit_finding
from nico.hosted_scanner_artifacts import attach_scanner_worker_artifacts


def test_bandit_credential_rule_is_real_blocker():
    triaged = classify_bandit_finding(
        {
            "test_id": "B105",
            "test_name": "hardcoded_password_string",
            "filename": "settings.py",
            "line_number": 12,
            "issue_severity": "LOW",
            "issue_confidence": "HIGH",
            "issue_text": "Possible hardcoded password.",
        }
    )

    assert triaged["classification"] == "real_blocker"
    assert triaged["priority"] == "critical"
    assert triaged["location"] == "settings.py:12"


def test_bandit_review_only_rule_gets_human_review_classification():
    triaged = classify_bandit_finding(
        {
            "test_id": "B404",
            "filename": "tools/run.py",
            "line_number": 3,
            "issue_severity": "LOW",
            "issue_confidence": "HIGH",
            "issue_text": "Consider possible security implications associated with subprocess module.",
        }
    )

    assert triaged["classification"] == "needs_human_review"
    assert triaged["false_positive_hint"] is True


def test_build_bandit_triage_counts_classes_and_rules():
    triage = build_bandit_triage(
        {
            "tools": {
                "bandit": {
                    "status": "completed",
                    "findings": [
                        {"test_id": "B105", "filename": "a.py", "line_number": 1, "issue_severity": "LOW", "issue_confidence": "HIGH"},
                        {"test_id": "B404", "filename": "b.py", "line_number": 2, "issue_severity": "LOW", "issue_confidence": "HIGH"},
                    ],
                }
            }
        }
    )

    assert triage["status"] == "blocking_findings"
    assert triage["finding_count"] == 2
    assert triage["blocking_count"] == 1
    assert triage["review_required_count"] == 1
    assert triage["by_rule"]["B105"] == 1


def test_bandit_triage_attaches_to_static_section_and_caps_score():
    result = {
        "status": "complete",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 90,
                "status": "green",
                "summary": "Static checks passed.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker in hosted mode."],
            }
        ],
        "findings": [],
    }
    artifact = {
        "tools": {
            "bandit": {
                "status": "completed",
                "findings": [
                    {
                        "test_id": "B105",
                        "test_name": "hardcoded_password_string",
                        "filename": "settings.py",
                        "line_number": 7,
                        "issue_severity": "LOW",
                        "issue_confidence": "HIGH",
                        "issue_text": "Possible hardcoded password.",
                    }
                ],
            },
            "semgrep": {"status": "completed", "findings": []},
            "eslint": {"status": "completed", "findings": []},
            "typescript": {"status": "completed", "findings": []},
        }
    }

    updated = attach_scanner_worker_artifacts(result, {"scanner_worker_artifact": artifact})
    static = updated["sections"][0]

    assert updated["bandit_triage"]["blocking_count"] == 1
    assert static["score"] <= 74
    assert any("Bandit triage classified" in item for item in static["evidence"])
    assert any("Bandit B105" in item for item in static["findings"])
