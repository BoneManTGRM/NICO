from nico.production_pilot_evidence_registry_v1 import qualify_production_pilot_registry


def _case(tier, index, **overrides):
    values = {
        "assessment_id": f"{tier}-assessment-{index}",
        "repository_identity": f"owner/{tier}-repo-{index}",
        "report_sha256": (str(index + 1) * 64)[:64],
        "deployment_sha": "a" * 40,
        "payment_receipt_id": f"receipt-{tier}-{index}",
        "client_reviewer": f"client-{index}",
        "completed_at": "2026-07-18T00:00:00Z",
        "amount_paid": {"express": 1000, "mid": 3000, "full": 7500}[tier],
        "production_run": True,
        "authorized_repository": True,
        "artifacts_downloaded": True,
        "manual_review_complete": True,
        "evidence_verified": True,
        "client_confirmed_value": True,
        "client_acted_on_report": True,
        "no_refund_requested": True,
        "material_false_positives": 0,
    }
    values.update(overrides)
    return values


def _registry():
    return {
        tier: [_case(tier, index) for index in range(3)]
        for tier in ("express", "mid", "full")
    }


def test_complete_registry_qualifies():
    result = qualify_production_pilot_registry(_registry())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_and_underpriced_cases_block():
    registry = _registry()
    registry["express"] = registry["express"][:2]
    registry["full"][0]["amount_paid"] = 500
    result = qualify_production_pilot_registry(registry)
    assert "express:insufficient_cases" in result["failures"]
    assert "full:case_0:below_minimum_price" in result["failures"]


def test_duplicate_receipts_and_assessments_block():
    registry = _registry()
    registry["mid"][1]["assessment_id"] = registry["mid"][0]["assessment_id"]
    registry["mid"][1]["payment_receipt_id"] = registry["mid"][0]["payment_receipt_id"]
    result = qualify_production_pilot_registry(registry)
    assert "mid:case_1:duplicate_assessment" in result["failures"]
    assert "mid:case_1:duplicate_receipt" in result["failures"]


def test_unverified_or_false_positive_case_blocks():
    registry = _registry()
    registry["full"][2]["evidence_verified"] = False
    registry["full"][2]["client_acted_on_report"] = False
    registry["full"][2]["material_false_positives"] = 1
    result = qualify_production_pilot_registry(registry)
    assert "full:case_2:evidence_verified:failed" in result["failures"]
    assert "full:case_2:client_acted_on_report:failed" in result["failures"]
    assert "full:case_2:material_false_positives" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_production_pilot_registry(_registry(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
