from nico.enterprise_security_compliance_gate_v1 import (
    REQUIRED_CONTROLS,
    qualify_enterprise_security_compliance,
)


def _evidence(**overrides):
    evidence = {control: True for control in REQUIRED_CONTROLS}
    evidence.update(
        reviewer="security-reviewer",
        reviewed_commit_sha="a" * 40,
        open_critical_findings=0,
        open_high_findings=0,
    )
    evidence.update(overrides)
    return evidence


def test_complete_security_package_qualifies():
    result = qualify_enterprise_security_compliance(_evidence())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_and_failed_controls_block():
    evidence = _evidence(tenant_isolation_verified=False)
    del evidence["incident_response_documented"]
    result = qualify_enterprise_security_compliance(evidence)
    assert "failed:tenant_isolation_verified" in result["failures"]
    assert "missing:incident_response_documented" in result["failures"]


def test_reviewer_sha_and_severe_findings_are_required():
    result = qualify_enterprise_security_compliance(
        _evidence(
            reviewer="",
            reviewed_commit_sha="",
            open_critical_findings=1,
            open_high_findings=2,
        )
    )
    assert "missing:reviewer" in result["failures"]
    assert "missing:reviewed_commit_sha" in result["failures"]
    assert "open_critical_findings" in result["failures"]
    assert "open_high_findings" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_enterprise_security_compliance(
        _evidence(), prior_release_allowed=False
    )
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
