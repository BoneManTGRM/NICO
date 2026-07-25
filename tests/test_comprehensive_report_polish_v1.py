from __future__ import annotations

from nico.comprehensive_report_polish_v1 import _clean_text, polish_assessment


def test_report_polish_removes_control_characters_and_summarizes_raw_failures() -> None:
    assessment = {
        "findings_register": [
            {
                "id": "osv-1",
                "priority": "P1",
                "category": "dependency",
                "title": "runtime: failed to create new OS thread (have 10 already; errno=11)\ufffe newosproc",
                "location": "Scanner execution boundary",
                "evidence": "tool=osv-scanner; verified=False",
                "impact": "raw stack",
                "confidence": "moderate",
            }
        ]
    }

    output = polish_assessment(assessment)
    finding = output["findings_register"][0]

    assert "\ufffe" not in _clean_text("before\ufffeafter")
    assert finding["title"] == "OSV scanner worker resource limit prevented completion"
    assert "newosproc" not in finding["title"].casefold()


def test_report_polish_groups_equivalent_unverified_code_locations() -> None:
    assessment = {
        "findings_register": [
            {
                "id": "code-1",
                "priority": "P1",
                "category": "code",
                "title": "python_eval_exec — Dynamic code execution should be reviewed.",
                "location": "apps/web/app/A.tsx:10",
                "evidence": "risk_pattern_hits=2",
                "impact": "possible unsafe api",
                "confidence": "moderate",
            },
            {
                "id": "code-2",
                "priority": "P1",
                "category": "code",
                "title": "python_eval_exec — Dynamic code execution should be reviewed.",
                "location": "apps/web/app/B.tsx:20",
                "evidence": "risk_pattern_hits=2",
                "impact": "possible unsafe api",
                "confidence": "moderate",
            },
        ]
    }

    output = polish_assessment(assessment)
    findings = output["findings_register"]

    assert len(findings) == 1
    assert findings[0]["priority"] == "P2"
    assert findings[0]["title"].endswith("(2 locations)")
    assert "apps/web/app/A.tsx:10" in findings[0]["location"]
    assert "apps/web/app/B.tsx:20" in findings[0]["location"]
    assert "not a confirmed defect" in findings[0]["impact"]


def test_report_polish_groups_mutable_action_tag_candidates() -> None:
    assessment = {
        "findings_register": [
            {
                "id": "semgrep-1",
                "priority": "P1",
                "category": "static",
                "title": "yaml.github-actions.security.github-actions-mutable-action-tag.github-actions\ufffe-mutable-action-tag",
                "location": ".github/workflows/a.yml:1",
                "evidence": "tool=semgrep; severity=medium; verified=False",
                "impact": "candidate",
                "confidence": "moderate",
            },
            {
                "id": "semgrep-2",
                "priority": "P1",
                "category": "static",
                "title": "yaml.github-actions.security.github-actions-mutable-action-tag.github-actions-mutable-action-tag",
                "location": ".github/workflows/b.yml:1",
                "evidence": "tool=semgrep; severity=medium; verified=False",
                "impact": "candidate",
                "confidence": "moderate",
            },
        ]
    }

    findings = polish_assessment(assessment)["findings_register"]

    assert len(findings) == 1
    assert findings[0]["title"] == "GitHub Actions workflow uses a mutable action tag (2 locations)"
    assert findings[0]["priority"] == "P2"
