from nico.client_value_scorecard_v1 import build_client_value_scorecard


def _finding(index, **overrides):
    value = {
        "title": f"Finding {index}",
        "evidence_reference": f"src/file.py:{index}",
        "business_consequence": "Operational loss or delayed delivery",
        "remediation": "Apply the bounded repair and verify with tests",
        "owner": "Engineering",
        "priority": "high",
        "confidence": 90,
        "evidence_verified": True,
        "estimated_exposure": 5000 + index,
        "estimated_remediation_cost": 1000,
    }
    value.update(overrides)
    return value


def test_scorecard_quantifies_verified_findings():
    findings = [_finding(index) for index in range(3)]
    result = build_client_value_scorecard(
        "express",
        findings,
        assessment_id="assessment-1",
        report_sha256="a" * 64,
    )
    assert result["status"] == "complete"
    assert result["verified_finding_count"] == 3
    assert result["total_estimated_exposure"] == 15003.0
    assert result["total_estimated_remediation_cost"] == 3000.0
    assert result["net_potential_value"] == 12003.0
    assert len(result["top_decisions"]) == 3


def test_unverified_finding_blocks_and_is_not_counted():
    findings = [_finding(index) for index in range(3)]
    findings[1]["evidence_verified"] = False
    result = build_client_value_scorecard(
        "express",
        findings,
        assessment_id="assessment-1",
        report_sha256="b" * 64,
    )
    assert result["status"] == "blocked"
    assert "finding_1:evidence_unverified" in result["failures"]
    assert result["verified_finding_count"] == 2


def test_missing_identity_and_thin_report_block():
    result = build_client_value_scorecard(
        "mid",
        [_finding(0)],
        assessment_id="",
        report_sha256="short",
    )
    assert "missing_assessment_id" in result["failures"]
    assert "invalid_report_sha256" in result["failures"]
    assert "insufficient_findings" in result["failures"]


def test_invalid_confidence_blocks_value_calculation():
    findings = [_finding(index) for index in range(3)]
    findings[0]["confidence"] = 120
    result = build_client_value_scorecard(
        "express",
        findings,
        assessment_id="assessment-2",
        report_sha256="c" * 64,
    )
    assert "finding_0:invalid_confidence" in result["failures"]
    assert result["verified_finding_count"] == 2
