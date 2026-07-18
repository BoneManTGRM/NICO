from nico.report_economic_value_gate_v1 import qualify_report_economic_value


def _finding(exposure=5000):
    return {
        "title": "Material delivery risk",
        "business_impact": "Could delay launch and increase operating cost.",
        "technical_evidence": "Repository path, commit, and failing control evidence.",
        "recommended_action": "Assign the named owner and complete the repair sequence.",
        "owner": "Engineering lead",
        "priority": "P1",
        "effort_estimate": "3-5 engineering days",
        "cost_or_loss_exposure": exposure,
        "confidence": "high",
    }


def _report(tier):
    count = {"express": 3, "mid": 7, "full": 12}[tier]
    return {
        "findings": [_finding() for _ in range(count)],
        "executive_decision_summary": "Proceed only after the P1 actions are complete.",
        "top_3_actions": ["Repair P1", "Verify tests", "Recheck deployment"],
        "90_day_roadmap": ["0-30 days", "31-60 days", "61-90 days"],
        "estimated_total_exposure": count * 5000,
        "estimated_remediation_budget": count * 1200,
        "evidence_coverage_percent": 92,
        "reviewer": "technical-reviewer",
        "snapshot_sha": "a" * 40,
    }


def _reports():
    return {tier: _report(tier) for tier in ("express", "mid", "full")}


def test_complete_decision_useful_reports_qualify():
    result = qualify_report_economic_value(_reports())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_tier_and_thin_report_block():
    reports = _reports()
    del reports["mid"]
    reports["express"]["findings"] = [_finding()]
    result = qualify_report_economic_value(reports)
    assert "mid:missing_report" in result["failures"]
    assert "express:insufficient_findings" in result["failures"]


def test_findings_require_action_evidence_and_economic_exposure():
    reports = _reports()
    reports["full"]["findings"][0] = _finding(exposure="unknown")
    reports["full"]["findings"][0]["recommended_action"] = ""
    result = qualify_report_economic_value(reports)
    assert "full:finding_0:missing:recommended_action" in result["failures"]
    assert "full:finding_0:invalid:cost_or_loss_exposure" in result["failures"]


def test_low_value_and_low_coverage_reports_block():
    reports = _reports()
    reports["mid"]["findings"] = [_finding(exposure=100) for _ in range(7)]
    reports["mid"]["evidence_coverage_percent"] = 70
    result = qualify_report_economic_value(reports)
    assert "mid:insufficient_high_value_findings" in result["failures"]
    assert "mid:low_evidence_coverage" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_report_economic_value(_reports(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
