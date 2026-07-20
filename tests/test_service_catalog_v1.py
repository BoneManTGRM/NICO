from nico.service_catalog_v1 import (
    COMPREHENSIVE,
    CUSTOMER_ASSESSMENT_SERVICES,
    EXPRESS,
    MONITOR_EXECUTE,
    apply_customer_service_identity,
    customer_assessment_catalog,
    full_customer_catalog,
    normalize_service_id,
)


def test_customer_assessment_catalog_exposes_only_express_and_comprehensive() -> None:
    assert CUSTOMER_ASSESSMENT_SERVICES == (EXPRESS, COMPREHENSIVE)
    catalog = customer_assessment_catalog()
    assert [item["id"] for item in catalog] == [EXPRESS, COMPREHENSIVE]
    assert all(item["category"] == "assessment" for item in catalog)
    assert all(item["customer_selectable"] is True for item in catalog)


def test_mid_and_full_are_backward_compatible_comprehensive_aliases() -> None:
    assert normalize_service_id("mid") == COMPREHENSIVE
    assert normalize_service_id("full") == COMPREHENSIVE
    assert normalize_service_id("deep") == COMPREHENSIVE
    assert normalize_service_id("comprehensive") == COMPREHENSIVE


def test_legacy_profile_is_retained_without_exposing_third_assessment_tier() -> None:
    payload = apply_customer_service_identity({"assessment_type": "full", "run_id": "fullrun_123"})
    assert payload["service_id"] == COMPREHENSIVE
    assert payload["service_tier"] == COMPREHENSIVE
    assert payload["customer_service_name"] == "NICO Comprehensive Technical Assessment"
    assert payload["internal_execution_profile"] == "full"
    assert payload["legacy_service_alias_preserved"] is True
    assert payload["customer_selectable_assessment"] is True


def test_monitor_execute_is_recurring_not_customer_assessment_tier() -> None:
    catalog = full_customer_catalog()
    monitor = next(item for item in catalog if item["id"] == MONITOR_EXECUTE)
    assert monitor["category"] == "recurring_operations"
    assert monitor["customer_selectable"] is False
    assert MONITOR_EXECUTE not in CUSTOMER_ASSESSMENT_SERVICES


def test_catalog_results_are_defensive_copies() -> None:
    first = customer_assessment_catalog()
    first[0]["customer_name"] = "mutated"
    second = customer_assessment_catalog()
    assert second[0]["customer_name"] == "NICO Express Technical Assessment"
