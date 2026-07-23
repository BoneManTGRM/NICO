from __future__ import annotations

from nico.comprehensive_score_assurance_ledger_v45 import apply_comprehensive_score_assurance_ledger_v45


def _payload() -> dict:
    return {
        "run_id": "comprun_score_assurance_test",
        "report_path": "full_run",
        "commit_sha": "a" * 40,
        "canonical_report_truth": {
            "technical_score": 86,
            "technical_band": "STRONG",
            "delivery_status": "Draft only",
        },
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 86,
                "presented_score": 86,
                "score_value": 86,
                "status": "yellow",
                "presented_status": "yellow",
                "findings": ["Review a verified complexity hotspot."],
                "evidence": ["Current-run complexity evidence is attached."],
                "unavailable": [],
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": 75,
                "presented_score": 75,
                "score_value": 75,
                "status": "supplemental",
                "presented_status": "supplemental",
                "findings": ["gitleaks timed out; partial output remains review-only."],
                "unavailable": [],
                "scanner_dispositions": {
                    "pip-audit": {"status": "completed_clean", "findings": 0, "source_statements": ["clean"]},
                    "bandit": {"status": "failed", "findings": 0, "source_statements": ["failed"]},
                    "gitleaks": {"status": "timeout", "findings": 3, "source_statements": ["timeout"]},
                },
            },
            {
                "id": "client_human_acceptance",
                "label": "Client / Human Acceptance",
                "score": None,
                "status": "gray",
                "presented_status": "gray",
                "findings": ["No approved final-report record exists."],
                "unavailable": ["Approval is pending."],
            },
        ],
    }


def test_comprehensive_uses_same_three_dimension_contract_as_express() -> None:
    result = apply_comprehensive_score_assurance_ledger_v45(_payload())
    architecture = next(item for item in result["sections"] if item["id"] == "architecture_debt")

    assert architecture["technical_band_label"] == "STRONG"
    assert architecture["technical_tone"] == "green"
    assert architecture["status"] == "strong"
    assert architecture["assurance_label"] == "REVIEW LIMITED"
    assert architecture["assurance_tone"] == "yellow"
    assert architecture["risk_label"] == "HUMAN TRIAGE REQUIRED"


def test_comprehensive_scanner_execution_is_not_a_pseudo_score() -> None:
    result = apply_comprehensive_score_assurance_ledger_v45(_payload())
    scanner = next(item for item in result["sections"] if item["id"] == "scanner_worker_evidence")

    assert scanner["score"] is None
    assert scanner["technical_score_display"] == "SUPPLEMENTAL · NOT SCORED"
    assert scanner["scanner_execution_summary"] == {
        "total": 3,
        "completed": 1,
        "failed": 1,
        "timed_out": 1,
        "not_configured": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    assert scanner["findings"] == []
    assert scanner["review_items"] == ["gitleaks timed out; partial output remains review-only."]


def test_comprehensive_acceptance_is_review_delivery_and_report_is_final() -> None:
    result = apply_comprehensive_score_assurance_ledger_v45(_payload())
    acceptance = next(item for item in result["sections"] if item["id"] == "client_human_acceptance")
    truth = result["canonical_report_truth"]

    assert acceptance["label"] == "Review and delivery"
    assert acceptance["section_group"] == "review_delivery"
    assert acceptance["technical_section"] is False
    assert acceptance["findings"] == []
    assert acceptance["unavailable"] == []
    assert truth["report_finality"] == "final"
    assert truth["approval_status"] == "pending_human_approval"
    assert truth["delivery_status"] == "blocked_pending_human_approval"
    assert result["client_delivery_allowed"] is False
