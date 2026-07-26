from __future__ import annotations

from pathlib import Path

import pytest

from nico.product_contract import (
    CUSTOMER_FACING_ASSESSMENT,
    INTERNAL_COMPLEXITY_CLASSES,
    MATURE_AUTOMATION_TARGETS,
    PRODUCT_NAME,
    RETIRED_PUBLIC_TIER_LABELS,
    maturity_target,
    normalized_complexity,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PRODUCT_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "ARCHITECTURE.md",
    ROOT / "docs" / "PROJECT_STATUS.md",
)


def test_canonical_customer_product_identity_is_singular() -> None:
    assert PRODUCT_NAME == "NICO Comprehensive Technical Assessment"
    assert CUSTOMER_FACING_ASSESSMENT == "comprehensive"
    assert INTERNAL_COMPLEXITY_CLASSES == ("small", "standard", "complex", "enterprise")
    assert len(set(INTERNAL_COMPLEXITY_CLASSES)) == len(INTERNAL_COMPLEXITY_CLASSES)


def test_public_product_documents_use_the_canonical_name_without_retired_tiers() -> None:
    retired_public_phrases = {
        phrase
        for retired in RETIRED_PUBLIC_TIER_LABELS
        for phrase in (
            f"nico {retired}",
            f"{retired} assessment",
            f"run {retired}",
            f"{retired} tier",
        )
    }
    retired_public_phrases.add("express/mid/full")

    for path in PUBLIC_PRODUCT_DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert PRODUCT_NAME in text, f"{path} does not name the canonical product"
        for phrase in retired_public_phrases:
            assert phrase not in lowered, f"{path} reintroduced retired public product phrase {phrase!r}"


def test_maturity_targets_are_bounded_and_include_fail_closed_claim_support() -> None:
    assert MATURE_AUTOMATION_TARGETS
    assert all(0.0 < value <= 1.0 for value in MATURE_AUTOMATION_TARGETS.values())
    assert maturity_target("material_claim_evidence_support") == 1.0
    assert maturity_target("cross_format_invariant_compliance") == 0.995
    with pytest.raises(KeyError):
        maturity_target("invented_metric")


@pytest.mark.parametrize("value", INTERNAL_COMPLEXITY_CLASSES)
def test_complexity_classification_is_internal_scope_not_report_quality(value: str) -> None:
    assert normalized_complexity(value.upper()) == value


def test_unknown_complexity_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported assessment complexity"):
        normalized_complexity("starter")
