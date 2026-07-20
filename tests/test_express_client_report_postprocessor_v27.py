from nico.express_client_report_postprocessor_v27 import (
    postprocess_express_client_reports,
    prepare_express_client_report,
)


def _result() -> dict:
    return {
        "maturity_signal": {"level": "Senior", "score": 90},
        "sections": [
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 95,
                "status": "green",
                "summary": "Current release-readiness checks are verified.",
                "findings": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 88,
                "status": "yellow",
                "summary": "Secret scanner evidence requires review.",
                "findings": ["gitleaks ended with status timeout; its output requires human review."],
            },
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 94,
                "status": "green",
                "summary": "Architecture evidence and complexity artifacts are available.",
                "findings": ["Complexity and high churn overlap in 52 delivery hotspot files."],
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": None,
                "status": "supplemental",
                "directly_scored": False,
                "findings": [],
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
                "directly_scored": False,
                "findings": [],
            },
        ],
        "reports": {
            "markdown": (
                "## Executive Summary\nOld generic summary.\n"
                "### Scanner Worker Evidence — SUPPLEMENTAL (None/100)\n"
                "### Client / Human Acceptance — GRAY (0/100)\n"
                "## Quick Wins\n- Generic quick win.\n"
                "## Medium-Term Plan\n- Generic plan.\n"
                "## Resourcing Recommendation\n- Generic resource.\n"
                "## Risk Register\n- Generic risk.\n"
                "## Verification Checklist\n- [ ] Generic check.\n"
            ),
            "html": (
                "<h3>Scanner Worker Evidence — SUPPLEMENTAL (None/100)</h3>"
                "<h3>Client / Human Acceptance — GRAY (0/100)</h3>"
            ),
        },
    }


def test_visible_not_scored_leakage_and_generic_sections_are_replaced() -> None:
    result = prepare_express_client_report(_result())
    result = postprocess_express_client_reports(result)
    markdown = result["reports"]["markdown"]
    html = result["reports"]["html"]

    assert "None/100" not in markdown
    assert "0/100" not in markdown
    assert "SUPPLEMENTAL (NOT SCORED)" in markdown
    assert "GRAY (NOT SCORED)" in markdown
    assert "Old generic summary" not in markdown
    assert "Generic quick win" not in markdown
    assert "Generic plan" not in markdown
    assert "Generic resource" not in markdown
    assert "Generic risk" not in markdown
    assert "Generic check" not in markdown
    assert "## Priority Actions" in markdown
    assert "gitleaks ended with status timeout" in markdown
    assert "0-30 days" in markdown
    assert "31-60 days" in markdown
    assert "61-90 days" in markdown
    assert "Cross-format drift" in markdown
    assert "Two consecutive same-SHA runs" in markdown
    assert "None/100" not in html
    assert "0/100" not in html
    assert result["express_client_report_postprocessor"]["status"] == "complete"


def test_priority_actions_ignore_not_scored_controls() -> None:
    result = _result()
    result["sections"][3]["findings"] = ["Scanner diagnostic should not become an executive priority."]
    prepared = prepare_express_client_report(result)
    assert all("Scanner diagnostic" not in item for item in prepared["priority_actions"])


def test_preparation_changes_pdf_source_fields_before_pdf_generation() -> None:
    prepared = prepare_express_client_report(_result())
    assert "Senior maturity level (90/100)" in prepared["executive_summary"]
    assert prepared["quick_wins"] == prepared["priority_actions"][:3]
    assert len(prepared["medium_term_plan"]) == 3
    assert any("Security-focused product engineer" in item for item in prepared["resourcing_recommendation"])
    assert any("Cross-format drift" in item for item in prepared["risk_register"])
    assert len(prepared["verification_checklist"]) == 7
