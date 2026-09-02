from nico.phase15_production_integration_v1 import (
    integrate_production_truth,
    normalize_production_scanner_records,
)

SHA = "a" * 40
DIGEST = "b" * 64


def _finding(fid: str):
    return {
        "finding_id": fid,
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "decision_title": "High-complexity code hotspot",
        "interpretation": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "business_impact": "Concentrated branching increases regression risk.",
        "recommendation": "Decompose the route.",
        "acceptance_criteria": ["Complexity is <= 30", " complexity is <= 30 "],
    }


def _bandit():
    return {
        "scanner": "bandit",
        "status": "failed",
        "commit_sha": SHA,
        "raw_exit_code": 1,
        "verified_complete": True,
        "exact_commit_match": True,
        "json_parseable": True,
        "artifact_sha256": DIGEST,
        "finding_count": 3,
        "command": "python -m bandit -r nico scripts -f json",
    }


def test_live_duplicate_pairs_are_collapsed_before_rendering():
    result = integrate_production_truth(
        {
            "commit_sha": SHA,
            "findings_register": [_finding("RISK-54DC2C8248A9")],
            "executive_risk_register": [_finding("RISK-P1-0A2FA160AB")],
        }
    )
    assert len(result["canonical_findings"]) == 1
    assert len(result["executive_risk_register"]) == 1
    assert set(result["canonical_findings"][0]["finding_aliases"]) == {
        "RISK-54DC2C8248A9",
        "RISK-P1-0A2FA160AB",
    }
    assert result["canonical_findings"][0]["title"] == "Reduce complexity in page.tsx"
    assert result["canonical_findings"][0]["acceptance_criteria"] == ["Complexity is <= 30"]


def test_bandit_exit_one_with_valid_json_is_completed_not_failed():
    [record] = normalize_production_scanner_records([_bandit()], expected_sha=SHA)
    assert record["status"] == "completed"
    assert record["capture_complete"] is True
    assert record["artifact_sha256"] == DIGEST
    assert record["exit_code"] == 1


def test_bandit_truth_is_visible_in_evidence_summary_and_report_projection():
    result = integrate_production_truth(
        {
            "commit_sha": SHA,
            "findings_register": [_finding("RISK-1")],
            "evidence_health_summary": {"scanner_records": [_bandit()]},
        }
    )
    bandit = next(
        item
        for item in result["evidence_health_summary"]["phase14_analyzer_evidence"]["analyzers"]
        if item["scanner"] == "bandit"
    )
    assert bandit["status"] == "completed"
    assert bandit["successful_passes"] == 1
    assert result["evidence_health_summary"]["completed_scanners"] == ["bandit"]
    assert result["analyzer_evidence_report"]["analyzers"]
    assert result["phase15_production_integration"]["bandit_record_ingested"] is True


def test_old_failed_record_without_completed_evidence_stays_failed():
    failed = {
        "scanner": "bandit",
        "status": "failed",
        "commit_sha": SHA,
        "raw_exit_code": 2,
        "verified_complete": False,
    }
    [record] = normalize_production_scanner_records([failed], expected_sha=SHA)
    assert record["status"] == "failed"
    assert record["capture_complete"] is False


def test_production_integration_is_idempotent_for_analyzer_evidence():
    first = integrate_production_truth(
        {
            "commit_sha": SHA,
            "evidence_health_summary": {"scanner_records": [_bandit()]},
        }
    )
    second = integrate_production_truth(first)

    assert second["analyzer_evidence_report"] == first["analyzer_evidence_report"]
    assert (
        second["evidence_health_summary"]["phase14_analyzer_evidence"]["rejected_records"]
        == []
    )
    assert second["phase15_production_integration"]["analyzer_contract_applied"] is True
    assert second["phase15_production_integration"]["bandit_record_ingested"] is True
