from nico.real_report_evidence_package_v1 import qualify_real_report_evidence_package


def _artifact():
    return {"uri": "artifact://report", "sha256": "a" * 64, "opened_successfully": True}


def _finding(index):
    return {
        "finding_id": f"finding-{index}",
        "evidence_pointer": f"src/module_{index}.py:10-20",
        "business_impact": "Material delivery, security, or operating-cost exposure.",
        "recommended_action": "Complete the evidence-backed remediation and verify the result.",
        "evidence_verified": True,
    }


def _package(tier, **overrides):
    count = {"express": 3, "mid": 7, "full": 12}[tier]
    value = {
        "assessment_id": f"{tier}-assessment",
        "repository_identity": "authorized-client/repository",
        "snapshot_sha": "b" * 40,
        "generated_at": "2026-07-18T00:00:00Z",
        "independent_reviewer": "named-reviewer",
        "review_rubric_version": "value-rubric-v1",
        "client_decision": "Fund the prioritized remediation plan.",
        "synthetic_fixture": False,
        "client_authorized": True,
        "manual_artifact_inspection_complete": True,
        "artifacts": {fmt: _artifact() for fmt in ("pdf", "html", "markdown")},
        "verified_findings": [_finding(i) for i in range(count)],
        "review_scores": {
            "accuracy": 92,
            "specificity": 90,
            "actionability": 94,
            "decision_utility": 91,
            "economic_value": 89,
        },
    }
    value.update(overrides)
    return value


def _packages():
    return {tier: _package(tier) for tier in ("express", "mid", "full")}


def test_complete_real_packages_qualify():
    result = qualify_real_report_evidence_package(_packages())
    assert result["delivery_allowed"] is True


def test_missing_tier_and_synthetic_package_block():
    packages = _packages()
    del packages["mid"]
    packages["express"]["synthetic_fixture"] = True
    result = qualify_real_report_evidence_package(packages)
    assert "mid:missing_package" in result["failures"]
    assert "express:synthetic_or_unverified_package" in result["failures"]


def test_missing_or_invalid_artifacts_block():
    packages = _packages()
    packages["full"]["artifacts"]["pdf"]["sha256"] = "bad"
    del packages["full"]["artifacts"]["html"]
    result = qualify_real_report_evidence_package(packages)
    assert "full:pdf:invalid_sha256" in result["failures"]
    assert "full:missing_artifact:html" in result["failures"]


def test_thin_or_unverified_findings_block():
    packages = _packages()
    packages["mid"]["verified_findings"] = [_finding(0)]
    packages["express"]["verified_findings"][0]["evidence_verified"] = False
    result = qualify_real_report_evidence_package(packages)
    assert "mid:insufficient_verified_findings" in result["failures"]
    assert "express:finding_0:evidence_unverified" in result["failures"]


def test_invalid_scores_and_prior_block_are_preserved():
    packages = _packages()
    packages["full"]["review_scores"]["economic_value"] = 120
    result = qualify_real_report_evidence_package(packages, prior_release_allowed=False)
    assert "full:invalid_score:economic_value" in result["failures"]
    assert "prior_release_block" in result["failures"]
