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
                "score": 86,
                "confidence": "high",
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "status": "supplemental",
                "score": None,
                "presented_score": None,
                "confidence": "review-limited",
            },
        ],
        "reports": {
            "markdown": "### Code Audit — GREEN (86/100)\n\n### Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)",
            "html": "<h3>Code Audit</h3><h3>Scanner Worker Evidence</h3>",
        },
    }


def test_contract_is_complete_and_scanner_is_not_scored() -> None:
    result = _result()
    contract = build_cross_format_contract(result)

    assert contract["status"] == "complete"
    assert contract["scanner_supplemental_not_scored"] is True
    scanner = next(item for item in contract["canonical_records"] if item["section_id"] == "scanner_worker_evidence")
    assert scanner["score"] is None
    assert scanner["directly_scored"] is False


def test_truth_fingerprint_is_deterministic_for_same_snapshot() -> None:
    first = build_cross_format_contract(_result())["truth_fingerprint"]
    second = build_cross_format_contract(_result())["truth_fingerprint"]
    assert first == second


def test_truth_fingerprint_changes_when_canonical_status_changes() -> None:
    first_result = _result()
    second_result = _result()
    second_result["sections"][0]["status"] = "yellow"

    first = build_cross_format_contract(first_result)["truth_fingerprint"]
    second = build_cross_format_contract(second_result)["truth_fingerprint"]
    assert first != second


def test_markdown_mismatch_degrades_contract() -> None:
    result = _result()
    result["reports"]["markdown"] = "### Code Audit — YELLOW (86/100)"
    contract = build_cross_format_contract(result)

    assert contract["status"] == "degraded"
    assert "code_audit" in contract["markdown_status_mismatches"]
    assert "scanner_worker_evidence" in contract["markdown_status_mismatches"]
