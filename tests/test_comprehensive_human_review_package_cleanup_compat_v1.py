from __future__ import annotations

from nico.comprehensive_human_review_package_cleanup_compat_v1 import (
    normalize_missing_fixture_identity,
)


def test_absent_legacy_fixture_identity_is_normalized() -> None:
    normalized = normalize_missing_fixture_identity(
        {"identity": {"repository": "BoneManTGRM/NICO"}}
    )

    assert normalized["identity"]["customer_id"] == "Not supplied"
    assert normalized["identity"]["project_id"] == "Not supplied"


def test_legacy_fixture_placeholders_are_normalized_for_validation() -> None:
    normalized = normalize_missing_fixture_identity(
        {
            "identity": {
                "customer_id": "default_customer",
                "project_id": "unknown_project",
            }
        }
    )

    assert normalized["identity"]["customer_id"] == "Not supplied"
    assert normalized["identity"]["project_id"] == "Not supplied"


def test_production_contract_does_not_hide_explicit_placeholders() -> None:
    normalized = normalize_missing_fixture_identity(
        {
            "identity": {
                "customer_id": "default_customer",
                "project_id": "unknown_project",
            },
            "v2_pipeline_contract": {
                "client_identity_placeholders_sanitized": True,
            },
        }
    )

    assert normalized["identity"]["customer_id"] == "default_customer"
    assert normalized["identity"]["project_id"] == "unknown_project"
