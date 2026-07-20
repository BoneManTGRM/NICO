from __future__ import annotations

from nico.express_cross_format_contract_v24 import build_cross_format_contract


def _result() -> dict:
    return {
        "repository": "owner/repo",
        "commit_sha": "abc123",
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "status": "green",
                "source_score": 90,
                "score": 86,
                "presented_score": 86,
                "confidence": "high",
                "directly_scored": True,
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "status": "supplemental",
                "score": None,
                "presented_score": None,
                "confidence": "review-limited",
                "directly_scored": False,
                "exclude_from_maturity": True,
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "status": "gray",
                "score": None,
                "presented_score": None,
                "confidence": "review-limited",
                "directly_scored": False,
                "exclude_from_maturity": True,
            },
        ],
        "reports": {
            "markdown": (
                "### Code Audit — GREEN (86/100)\n\n"
                "### Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)\n\n"
                "### Client / Human Acceptance — GRAY (NOT SCORED)"
            ),
            "html": (
                "<h3>Code Audit — GREEN (86/100)</h3>"
                "<h3>Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)</h3>"
                "<h3>Client / Human Acceptance — GRAY (NOT SCORED)</h3>"
            ),
        },
    }


def test_contract_is_complete_and_not_scored_controls_are_excluded() -> None:
    result = _result()
    contract = build_cross_format_contract(result)

    assert contract["status"] == "complete"
    assert contract["scanner_supplemental_not_scored"] is True
    assert contract["not_scored_controls_excluded"] is True
    by_id = {item["section_id"]: item for item in contract["canonical_records"]}
    assert by_id["code_audit"]["source_score"] == 90
    assert by_id["code_audit"]["score"] == 86
    for section_id in ("scanner_worker_evidence", "client_acceptance"):
        assert by_id[section_id]["score"] is None
        assert by_id[section_id]["directly_scored"] is False
        assert by_id[section_id]["score_label"] == "NOT SCORED"


def test_truth_fingerprint_is_deterministic_for_same_snapshot() -> None:
    first = build_cross_format_contract(_result())["truth_fingerprint"]
    second = build_cross_format_contract(_result())["truth_fingerprint"]
    assert first == second


def test_truth_fingerprint_changes_when_canonical_score_changes() -> None:
    first_result = _result()
    second_result = _result()
    second_result["sections"][0]["score"] = 85
    second_result["sections"][0]["presented_score"] = 85

    first = build_cross_format_contract(first_result)["truth_fingerprint"]
    second = build_cross_format_contract(second_result)["truth_fingerprint"]
    assert first != second


def test_markdown_status_or_score_mismatch_degrades_contract() -> None:
    result = _result()
    result["reports"]["markdown"] = (
        "### Code Audit — YELLOW (74/100)\n\n"
        "### Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)\n\n"
        "### Client / Human Acceptance — GRAY (NOT SCORED)"
    )
    contract = build_cross_format_contract(result)

    assert contract["status"] == "degraded"
    assert "code_audit" in contract["markdown_status_score_mismatches"]


def test_html_numeric_mismatch_degrades_contract() -> None:
    result = _result()
    result["reports"]["html"] = result["reports"]["html"].replace("GREEN (86/100)", "GREEN (74/100)")
    contract = build_cross_format_contract(result)

    assert contract["status"] == "degraded"
    assert "code_audit" in contract["html_status_score_mismatches"]
