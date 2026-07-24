from __future__ import annotations

from nico.express_score_assurance_export_v1 import publish_score_assurance_exports


def _result() -> dict:
    return {
        "human_review_required": True,
        "sections": [
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 92,
                "presented_score": 92,
                "status": "yellow",
                "evidence": ["Current release checks passed."],
                "findings": ["Historical workflow reliability remains open."],
                "unavailable": [],
            },
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "presented_score": 86,
                "status": "green",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 74,
                "presented_score": 74,
                "status": "green",
                "evidence": ["Exact-snapshot complexity evidence attached."],
                "findings": [],
                "unavailable": ["Release-readiness lift evidence is incomplete."],
            },
        ],
        "reports": {
            "markdown": (
                "# Existing report\n\n"
                "### CI/CD Analysis — YELLOW (92/100)\n\n"
                "### Code Audit — GREEN (86/100)\n\n"
                "### Velocity / Complexity — GREEN (74/100)\n"
            ),
            "html": (
                "<html><body><h1>Existing report</h1>"
                "<h3>CI/CD Analysis — YELLOW (92/100)</h3>"
                "<h3>Code Audit — GREEN (86/100)</h3>"
                "<h3>Velocity / Complexity — GREEN (74/100)</h3>"
                "</body></html>"
            ),
        },
    }


def test_publishes_independent_score_and_assurance_tables() -> None:
    result = publish_score_assurance_exports(_result())
    markdown = result["reports"]["markdown"]
    html = result["reports"]["html"]

    assert "Technical Score and Assurance" in markdown
    assert "CI/CD Analysis | 92/100 | EXCEPTIONAL | REVIEW LIMITED | YELLOW" in markdown
    assert "Code Audit | 86/100 | STRONG | VERIFIED | GREEN" in markdown
    assert "Velocity / Complexity | 74/100 | MODERATE | VERIFIED | GREEN" in markdown
    assert 'data-nico-score-assurance="separate"' in html
    assert "EXCEPTIONAL" in html
    assert "REVIEW LIMITED" in html
    assert result["sections"][0]["status"] == "yellow"
    assert result["score_assurance_export"]["score_and_assurance_are_independent"] is True


def test_rewrites_legacy_status_colored_headings_without_weakening_assurance() -> None:
    result = publish_score_assurance_exports(_result())
    markdown = result["reports"]["markdown"]
    html = result["reports"]["html"]

    assert "### CI/CD Analysis — EXCEPTIONAL (92/100)" in markdown
    assert "**Evidence assurance:** REVIEW LIMITED · **Risk disposition:** YELLOW" in markdown
    assert "### Code Audit — STRONG (86/100)" in markdown
    assert "**Evidence assurance:** VERIFIED · **Risk disposition:** GREEN" in markdown
    assert "### Velocity / Complexity — MODERATE (74/100)" in markdown
    assert "CI/CD Analysis — YELLOW (92/100)" not in markdown
    assert "Code Audit — GREEN (86/100)" not in markdown
    assert "Velocity / Complexity — GREEN (74/100)" not in markdown
    assert "CI/CD Analysis — EXCEPTIONAL (92/100)" in html
    assert "data-nico-section-assurance" in html


def test_verified_green_requires_score_threshold_and_verified_assurance() -> None:
    result = publish_score_assurance_exports(_result())
    export = result["score_assurance_export"]

    assert export["verified_green_controls"] == ["code_audit"]
    assert "ci_cd" in export["green_blockers"]
    assert "velocity_complexity" in export["green_blockers"]
    assert any("at least 80" in item for item in export["green_blockers"]["velocity_complexity"])
    assert "Verified Green Readiness" in result["reports"]["markdown"]


def test_export_is_idempotent() -> None:
    result = publish_score_assurance_exports(_result())
    publish_score_assurance_exports(result)
    assert result["reports"]["markdown"].count("NICO_SCORE_ASSURANCE_START") == 1
    assert result["reports"]["html"].count("NICO_SCORE_ASSURANCE_HTML_START") == 1
    assert result["reports"]["markdown"].count("Evidence assurance:") == 3
