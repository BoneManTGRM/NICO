from nico.blind_expert_value_validation_v1 import qualify_blind_expert_validation


def sample_case(**changes):
    item = {
        "real_repository": True,
        "reviewer_blinded": True,
        "evidence_verified": True,
        "material_false_positives": 0,
        "report_sha256": "a" * 64,
        "assessment_id": "assessment-1",
        "reviewer": "independent-expert",
        "client_decision": "fund remediation",
    }
    item.update(changes)
    return item


def sample_record(tier, **changes):
    item = {
        "cases": [sample_case(assessment_id=f"{tier}-{n}") for n in range(3)],
        "median_expert_score": {"express": 80, "mid": 86, "full": 92}[tier],
        "median_willingness_to_pay": {"express": 1500, "mid": 4500, "full": 10000}[tier],
        "client_action_confirmed": True,
        "comparison_to_human_consultant_complete": True,
    }
    item.update(changes)
    return item


def sample_evidence():
    return {tier: sample_record(tier) for tier in ("express", "mid", "full")}


def test_complete_validation_qualifies():
    assert qualify_blind_expert_validation(sample_evidence())["delivery_allowed"] is True


def test_missing_cases_block():
    evidence = sample_evidence()
    evidence["mid"]["cases"] = [sample_case()]
    result = qualify_blind_expert_validation(evidence)
    assert "mid:insufficient_real_cases" in result["failures"]


def test_bad_case_blocks():
    evidence = sample_evidence()
    evidence["full"]["cases"][0] = sample_case(reviewer_blinded=False, evidence_verified=False, material_false_positives=1)
    result = qualify_blind_expert_validation(evidence)
    assert "full:case_0:reviewer_not_blinded" in result["failures"]
    assert "full:case_0:evidence_not_verified" in result["failures"]
    assert "full:case_0:material_false_positives" in result["failures"]


def test_low_value_blocks():
    evidence = sample_evidence()
    evidence["express"] = sample_record("express", median_expert_score=50, median_willingness_to_pay=100, client_action_confirmed=False, comparison_to_human_consultant_complete=False)
    result = qualify_blind_expert_validation(evidence)
    assert "express:low_median_expert_score" in result["failures"]
    assert "express:low_willingness_to_pay" in result["failures"]


def test_prior_block_is_preserved():
    result = qualify_blind_expert_validation(sample_evidence(), prior_release_allowed=False)
    assert "prior_release_block" in result["failures"]
