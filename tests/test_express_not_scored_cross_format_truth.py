from nico.express_canonical_truth_finalization_v23 import finalize_express_truth


def test_not_scored_controls_drop_numeric_scores_from_markdown_and_html() -> None:
    result = {
        "sections": [
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": 27,
                "status": "red",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
                "evidence": [],
                "findings": [],
                "unavailable": ["No approval record was found."],
            },
        ],
        "reports": {
            "markdown": (
                "### Scanner Worker Evidence — RED (27/100)\n"
                "- **Scanner Worker Evidence**: red\n"
                "### Client / Human Acceptance — GRAY (0/100)\n"
                "- **Client / Human Acceptance**: gray\n"
            ),
            "html": (
                "<h3>Scanner Worker Evidence — RED (27/100)</h3>"
                "<h3>Client / Human Acceptance — GRAY (0/100)</h3>"
            ),
        },
    }

    finalized = finalize_express_truth(result)
    markdown = finalized["reports"]["markdown"]
    html = finalized["reports"]["html"]

    assert "Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)" in markdown
    assert "Client / Human Acceptance — GRAY (NOT SCORED)" in markdown
    assert "27/100" not in markdown
    assert "0/100" not in markdown
    assert "Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)" in html
    assert "Client / Human Acceptance — GRAY (NOT SCORED)" in html
    assert "27/100" not in html
    assert "0/100" not in html


def test_approved_acceptance_keeps_score_in_cross_format_outputs() -> None:
    result = {
        "sections": [
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 96,
                "status": "green",
                "approved": True,
                "evidence": ["Approved by human reviewer."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "reports": {
            "markdown": "### Client / Human Acceptance — RED (96/100)\n",
            "html": "<h3>Client / Human Acceptance — RED (96/100)</h3>",
        },
    }

    finalized = finalize_express_truth(result)
    assert "Client / Human Acceptance — GREEN (96/100)" in finalized["reports"]["markdown"]
    assert "Client / Human Acceptance — GREEN (96/100)" in finalized["reports"]["html"]
