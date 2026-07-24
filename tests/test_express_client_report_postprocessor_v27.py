from nico.express_client_report_postprocessor_v27 import (
    postprocess_express_client_reports,
    prepare_express_client_report,
)


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
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 94,
                "status": "green",
                "summary": "Architecture evidence is present, with concentrated complexity hotspots requiring planned remediation.",
                "findings": ["Complexity hotspot: nico/hosted_assessment.py requires decomposition."],
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
        "maturity_signal": {"level": "Senior", "score": 90},
        "reports": {
            "markdown": (
                "## Executive Summary\nGeneric summary.\n"
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
    source = _result()
    prepare_express_client_report(source)
    result = postprocess_express_client_reports(source)
    markdown = result["reports"]["markdown"]
    html = result["reports"]["html"]

    assert "Scanner Worker Evidence" not in markdown
    assert "Client / Human Acceptance" not in markdown
    assert "Scanner Assurance Ledger — SUPPLEMENTAL (NOT SCORED)" in markdown
    assert "Review and Delivery — PENDING HUMAN APPROVAL (NOT SCORED)" in markdown
    assert "Generic summary" not in markdown
    assert "Generic quick win" not in markdown
    assert "Generic plan" not in markdown
    assert "Generic resource" not in markdown
    assert "Generic risk" not in markdown
    assert "Generic check" not in markdown
    assert "## Priority Actions" in markdown
    assert "gitleaks ended with status timeout" in markdown
    assert "0-30 days" in markdown
    assert "Maintain verified scanner-worker artifacts" in markdown
    assert "Product quality engineer" in markdown
    assert "Cross-format drift" in markdown
    assert "Two consecutive same-SHA runs" in markdown
    assert "- [ ] [ ]" not in markdown
    assert "Scanner Worker Evidence" not in html
    assert "Client / Human Acceptance" not in html
    assert "Scanner Assurance Ledger — SUPPLEMENTAL (NOT SCORED)" in html
    assert "Review and Delivery — PENDING HUMAN APPROVAL (NOT SCORED)" in html
    assert result["express_client_report_postprocessor"]["status"] == "complete"
    assert result["service_id"] == "express"
    assert result["customer_service_name"] == "NICO Express Technical Assessment"
    assert result["internal_execution_profile"] == "express"


def test_priority_actions_ignore_not_scored_controls() -> None:
    result = _result()
    result["sections"][2]["findings"] = ["Scanner diagnostic should not become an executive priority."]
    prepare_express_client_report(result)
    finalized = postprocess_express_client_reports(result)
    markdown = finalized["reports"]["markdown"]
    assert "Scanner diagnostic should not become an executive priority" not in markdown


def test_pre_generation_fields_are_ready_for_pdf_renderer() -> None:
    result = prepare_express_client_report(_result())
    assert result["executive_summary"].startswith("NICO assessed the exact authorized repository snapshot")
    assert result["priority_actions"]
    assert result["quick_wins"]
    assert len(result["medium_term_plan"]) >= 4
    assert any("Maintain verified scanner-worker artifacts" in item for item in result["medium_term_plan"])
    assert result["resourcing_recommendation"]
    assert result["risk_register"]
    assert result["verification_checklist"]
    assert result["service_tier"] == "express"


def test_existing_evidence_ledger_plan_item_is_preserved() -> None:
    result = _result()
    result["medium_term_plan"] = ["Evidence ledger attached before report rebuild; retain the verified ledger artifact."]
    prepared = prepare_express_client_report(result)
    assert any("Evidence ledger attached" in item for item in prepared["medium_term_plan"])
