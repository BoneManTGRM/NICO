from __future__ import annotations

from nico.comprehensive_human_review_package_cleanup_compat_v1 import (
    normalize_missing_fixture_identity,
)


def test_only_absent_fixture_identity_is_normalized() -> None:
    normalized = normalize_missing_fixture_identity(
        {"identity": {"repository": "BoneManTGRM/NICO"}}
    )

    assert normalized["identity"]["customer_id"] == "Not supplied"
    assert normalized["identity"]["project_id"] == "Not supplied"


def test_explicit_placeholders_are_not_hidden_by_compatibility_layer() -> None:
    normalized = normalize_missing_fixture_identity(
        {
            "identity": {
                "customer_id": "default_customer",
                "project_id": "unknown_project",
            }
        }
    )

    assert normalized["identity"]["customer_id"] == "default_customer"
    assert normalized["identity"]["project_id"] == "unknown_project"
