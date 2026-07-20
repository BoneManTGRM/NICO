from nico.comprehensive_capability_registry import CAPABILITY_REGISTRY, comprehensive_capability_registry, execution_plan, validate_capability_registry
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES, EXPRESS_STAGES


def test_registry_covers_all_stages_in_order():
    result = validate_capability_registry()
    assert result["status"] == "valid"
    assert tuple(CAPABILITY_REGISTRY) == COMPREHENSIVE_STAGES
    assert result["express_stages_first"] is True


def test_each_stage_has_required_source():
    for stage, item in CAPABILITY_REGISTRY.items():
        assert stage in COMPREHENSIVE_STAGES
        assert item["required"] is True
        assert item["capability"]
        assert item["sources"]


def test_execution_plan_starts_with_express():
    plan = execution_plan()
    assert [item["stage_id"] for item in plan[:len(EXPRESS_STAGES)]] == list(EXPRESS_STAGES)
    assert [item["stage_id"] for item in plan] == list(COMPREHENSIVE_STAGES)


def test_registry_returns_defensive_copy():
    copied = comprehensive_capability_registry()
    copied[EXPRESS_STAGES[0]]["capability"] = "changed"
    assert CAPABILITY_REGISTRY[EXPRESS_STAGES[0]]["capability"] == "authorization"


def test_missing_stage_is_invalid():
    broken = comprehensive_capability_registry()
    broken.pop(EXPRESS_STAGES[0])
    result = validate_capability_registry(broken)
    assert result["status"] == "invalid"
    assert EXPRESS_STAGES[0] in result["missing_stages"]


def test_safety_boundaries_remain_fixed():
    result = validate_capability_registry()
    assert result["customer_service_id"] == "comprehensive"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
