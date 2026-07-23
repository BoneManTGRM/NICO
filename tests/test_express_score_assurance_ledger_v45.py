from __future__ import annotations

from nico.express_score_assurance_ledger_v45 import apply_express_score_assurance_ledger_v45


def _section(section_id: str, score: int | None, status: str, *, findings: list[str] | None = None) -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "presented_score": score,
        "score_value": score,
        "status": status,
        "presented_status": status,
        "directly_scored": score is not None,
        "exclude_from_maturity": score is None,
        "evidence": [],
        "findings": findings or [],
        "unavailable": [],
    }


def _payload() -> dict:
    ci = _section("ci_cd", 92, "review_limited", findings=["Historical workflow reliability advisory."])
    architecture = _section("architecture_debt", 86, "review_limited", findings=["Human review of a complexity hotspot is recommended."])
    scanner = _section("scanner_worker_evidence", 75, "supplemental", findings=[
        "bandit ended with status failed; review scanner output.",
        "gitleaks ended with status timeout; partial output is review-only.",
    ])
    scanner["scanner_dispositions"] = {
        "pip-audit": {"status": "completed_clean", "findings": 0, "source_statements": ["pip-audit status=completed; findings=0"]},
        "npm-audit": {"status": "completed_clean", "findings": 0, "source_statements": ["npm-audit status=completed; findings=0"]},
        "osv-scanner": {"status": "completed_findings", "findings": 1, "source_statements": ["osv-scanner status=completed; findings=1"]},
        "bandit": {"status": "failed", "findings": 0, "source_statements": ["bandit status=failed"]},
        "semgrep": {"status": "completed_findings", "findings": 114, "source_statements": ["semgrep status=completed; findings=114"]},
        "eslint": {"status": "unavailable", "findings": 0, "source_statements": ["No ESLint configuration exists"]},
        "typescript": {"status": "completed_findings", "findings": 1, "source_statements": ["typescript status=completed; findings=1"]},
        "gitleaks": {"status": "timeout", "findings": 10, "source_statements": ["gitleaks timed out"]},
        "trufflehog": {"status": "completed_findings", "findings": 1, "source_statements": ["trufflehog status=completed; findings=1"]},
    }
    acceptance = _section("client_acceptance", None, "human_review_pending", findings=["No approval record exists."])
    return {
        "run_id": "express_run_test",
        "commit_sha": "a" * 40,
        "sections": [ci, architecture, scanner, acceptance],
    }


def test_high_technical_scores_use_their_numeric_band_not_assurance_color() -> None:
    result = apply_express_score_assurance_ledger_v45(_payload())
    ci = next(item for item in result["sections"] if item["id"] == "ci_cd")
    architecture = next(item for item in result["sections"] if item["id"] == "architecture_debt")

    assert ci["technical_band_label"] == "EXCEPTIONAL"
    assert ci["technical_tone"] == "green"
    assert ci["status"] == "exceptional"
    assert ci["assurance_label"] == "REVIEW LIMITED"
    assert ci["assurance_tone"] == "yellow"
    assert ci["risk_label"] == "ADVISORY FINDINGS"

    assert architecture["technical_band_label"] == "STRONG"
    assert architecture["technical_tone"] == "green"
    assert architecture["status"] == "strong"
    assert architecture["assurance_label"] == "REVIEW LIMITED"


def test_scanner_worker_is_an_assurance_ledger_without_a_pseudo_score() -> None:
    result = apply_express_score_assurance_ledger_v45(_payload())
    scanner = next(item for item in result["sections"] if item["id"] == "scanner_worker_evidence")

    assert scanner["score"] is None
    assert scanner["presented_score"] is None
    assert scanner["score_value"] is None
    assert scanner["display_status"] == "SUPPLEMENTAL · NOT SCORED"
    assert scanner["technical_score_display"] == "SUPPLEMENTAL · NOT SCORED"
    assert scanner["scanner_execution_denominator"] == 9
    assert scanner["scanner_execution_summary"] == {
        "total": 9,
        "completed": 6,
        "failed": 1,
        "timed_out": 1,
        "not_configured": 1,
        "unavailable": 0,
        "unknown": 0,
    }
    assert "6 completed · 1 failed · 1 timed out · 1 not configured" in scanner["summary"]
    assert scanner["findings"] == []
    assert len(scanner["review_items"]) == 2
    assert len(scanner["analyzer_ledger"]) == 9
    assert result["scanner_assurance_ledger"]["technical_maturity_effect"] == "excluded_to_prevent_double_counting"


def test_failed_and_timed_out_tools_cannot_claim_clean_results() -> None:
    result = apply_express_score_assurance_ledger_v45(_payload())
    ledger = {item["tool"]: item for item in result["scanner_assurance_ledger"]["analyzers"]}

    assert ledger["bandit"]["lifecycle_result"] == "failed"
    assert ledger["bandit"]["clean_claim_eligible"] is False
    assert ledger["gitleaks"]["lifecycle_result"] == "timed_out"
    assert ledger["gitleaks"]["clean_claim_eligible"] is False
    assert ledger["eslint"]["lifecycle_result"] == "not_configured"
    assert ledger["eslint"]["in_scope"] is False
    assert ledger["pip-audit"]["clean_claim_eligible"] is True


def test_client_acceptance_is_review_and_delivery_not_technical_maturity() -> None:
    result = apply_express_score_assurance_ledger_v45(_payload())
    acceptance = next(item for item in result["sections"] if item["id"] == "client_acceptance")

    assert acceptance["label"] == "Review and delivery"
    assert acceptance["section_group"] == "review_delivery"
    assert acceptance["technical_section"] is False
    assert acceptance["score"] is None
    assert acceptance["display_status"] == "PENDING HUMAN APPROVAL · NOT SCORED"
    assert acceptance["findings"] == []
    assert acceptance["unavailable"] == []
    assert result["review_and_delivery"]["client_delivery_allowed"] is False


def test_contract_records_three_independent_dimensions() -> None:
    result = apply_express_score_assurance_ledger_v45(_payload())
    contract = result["score_assurance_risk_contract"]

    assert contract["technical_score_controls_color"] is True
    assert contract["assurance_is_independent"] is True
    assert contract["risk_is_independent"] is True
    assert contract["scanner_ledger_not_scored"] is True
    assert contract["acceptance_outside_technical_maturity"] is True
    assert contract["client_delivery_allowed"] is False
