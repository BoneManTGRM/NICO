from nico.express_client_report_postprocessor_v27 import postprocess_express_client_reports


def _result() -> dict:
    return {
        "sections": [
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 88,
                "status": "yellow",
                "findings": ["gitleaks ended with status timeout; its output requires human review."],
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
                "### Scanner Worker Evidence — SUPPLEMENTAL (None/100)\n"
                "### Client / Human Acceptance — GRAY (0/100)\n"
                "## Quick Wins\n- Generic quick win.\n"
                "## Medium-Term Plan\n- Generic plan.\n"
                "## Verification Checklist\n- [ ] Generic check.\n"
            ),
            "html": (
                "<h3>Scanner Worker Evidence — SUPPLEMENTAL (None/100)</h3>"
                "<h3>Client / Human Acceptance — GRAY (0/100)</h3>"
            ),
        },
    }


def test_visible_not_scored_leakage_and_generic_sections_are_replaced() -> None:
    result = postprocess_express_client_reports(_result())
    markdown = result["reports"]["markdown"]
    html = result["reports"]["html"]

    assert "None/100" not in markdown
    assert "0/100" not in markdown
    assert "SUPPLEMENTAL (NOT SCORED)" in markdown
    assert "GRAY (NOT SCORED)" in markdown
    assert "Generic quick win" not in markdown
    assert "Generic plan" not in markdown
    assert "Generic check" not in markdown
    assert "## Priority Actions" in markdown
    assert "gitleaks ended with status timeout" in markdown
    assert "None/100" not in html
    assert "0/100" not in html
    assert result["express_client_report_postprocessor"]["status"] == "complete"


def test_priority_actions_ignore_not_scored_controls() -> None:
    result = _result()
    result["sections"][1]["findings"] = ["Scanner diagnostic should not become an executive priority."]
    finalized = postprocess_express_client_reports(result)
    markdown = finalized["reports"]["markdown"]
    assert "Scanner diagnostic should not become an executive priority" not in markdown
