from nico.phase15_finding_quality_v1 import prioritize_findings, quality_finding


def _finding(index: int, *, severity: str = "medium", release_blocking: bool = False):
    return {
        "finding_id": f"F-{index}",
        "title": f"Distinct risk {index}",
        "severity": severity,
        "likelihood": "likely",
        "confidence": "high",
        "business_impact": f"Business impact {index}",
        "release_blocking": release_blocking,
        "evidence": f"fact {index}",
        "interpretation": f"interpretation {index}",
        "inference": f"inference {index}",
        "recommendation": f"recommendation {index}",
        "owner_role": "Platform engineering",
        "effort": "M",
        "residual_risk": "Low after remediation",
        "acceptance_criteria": [f"Measure {index} passes"],
    }


def test_p1_requires_release_blocking_or_materially_severe_support():
    ordinary = quality_finding(_finding(1, severity="medium"))
    blocker = quality_finding(_finding(2, severity="high", release_blocking=True))
    assert ordinary["priority"] != "P1"
    assert blocker["priority"] == "P1"
    assert "release-blocking" in blocker["ranking_reason"]


def test_missing_priority_support_is_downgraded_and_exposed():
    finding = _finding(1, severity="critical")
    finding.pop("confidence")
    result = quality_finding(finding)
    assert result["priority"] == "P3"
    assert result["quality_complete"] is False
    assert result["quality_gaps"] == ["confidence"]


def test_fact_interpretation_inference_and_recommendation_remain_separate():
    result = quality_finding(_finding(1))
    assert result["fact"] == "fact 1"
    assert result["interpretation"] == "interpretation 1"
    assert result["inference"] == "inference 1"
    assert result["recommendation"] == "recommendation 1"


def test_top5_next10_and_backlog_are_deterministic():
    findings = [_finding(index, severity="high" if index < 3 else "medium") for index in range(18)]
    first = prioritize_findings(reversed(findings))
    second = prioritize_findings(findings)
    assert [item["finding_id"] for item in first["all_findings"]] == [item["finding_id"] for item in second["all_findings"]]
    assert len(first["top_5"]) == 5
    assert len(first["next_10"]) == 10
    assert len(first["backlog"]) == 3
    assert first["generic_title_collision"] is False


def test_every_finding_has_unique_evidence_bound_ranking_reason():
    findings = [_finding(1, severity="critical", release_blocking=True), _finding(2, severity="medium")]
    result = prioritize_findings(findings)
    reasons = [item["ranking_reason"] for item in result["all_findings"]]
    assert len(set(reasons)) == len(reasons)
