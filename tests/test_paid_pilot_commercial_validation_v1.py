from nico.paid_pilot_commercial_validation_v1 import qualify_paid_pilot_commercial_validation


def _case(tier, index, **overrides):
    price = {"express": 1200, "mid": 3500, "full": 8500}[tier]
    score = {"express": 82, "mid": 88, "full": 93}[tier]
    record = {
        "client_id": f"client-{tier}-{index}",
        "assessment_id": f"assessment-{tier}-{index}",
        "report_sha256": "a" * 64,
        "invoice_id": f"invoice-{tier}-{index}",
        "payment_date": "2026-07-18",
        "client_reviewer": "client-technical-lead",
        "client_decision": "Approved remediation plan",
        "amount_paid": price,
        "client_value_score": score,
        "real_repository": True,
        "evidence_verified": True,
        "material_false_positive": False,
        "client_acted_on_report": True,
        "refund_requested": False,
        "renewal_or_follow_on_intent": index == 0,
    }
    record.update(overrides)
    return record


def _pilots():
    return {
        "express": [_case("express", i) for i in range(3)],
        "mid": [_case("mid", i) for i in range(3)],
        "full": [_case("full", i) for i in range(2)],
    }


def test_complete_paid_pilot_cohort_qualifies():
    result = qualify_paid_pilot_commercial_validation(_pilots())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_or_underpriced_cases_block():
    pilots = _pilots()
    pilots["express"] = pilots["express"][:2]
    pilots["mid"][0]["amount_paid"] = 500
    result = qualify_paid_pilot_commercial_validation(pilots)
    assert "express:insufficient_paid_cases" in result["failures"]
    assert "mid:case_0:below_minimum_price" in result["failures"]


def test_low_value_false_positive_and_refund_block():
    pilots = _pilots()
    pilots["full"][0].update(
        client_value_score=40,
        material_false_positive=True,
        refund_requested=True,
    )
    result = qualify_paid_pilot_commercial_validation(pilots)
    assert "full:case_0:low_client_value_score" in result["failures"]
    assert "full:case_0:material_false_positive" in result["failures"]
    assert "full:case_0:refund_requested" in result["failures"]


def test_action_and_follow_on_intent_are_required():
    pilots = _pilots()
    for case in pilots["mid"]:
        case["client_acted_on_report"] = False
        case["renewal_or_follow_on_intent"] = False
    result = qualify_paid_pilot_commercial_validation(pilots)
    assert "mid:low_client_action_rate" in result["failures"]
    assert "mid:no_renewal_or_follow_on_intent" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_paid_pilot_commercial_validation(_pilots(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
