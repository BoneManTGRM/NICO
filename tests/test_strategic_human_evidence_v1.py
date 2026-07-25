from __future__ import annotations

import pytest

from nico.strategic_human_evidence_v1 import (
    MODULES,
    human_evidence_module,
    normalize_strategic_human_evidence,
)


def test_missing_human_context_is_explicitly_not_assessed() -> None:
    package = normalize_strategic_human_evidence(None)

    assert package["status"] == "not_assessed"
    assert package["provided_module_ids"] == []
    assert package["repository_inference_prohibited"] is True
    assert package["status_counts"]["not_assessed"] == len(MODULES)
    assert len(package["human_evidence_sha256"]) == 64


def test_explicit_statements_records_and_references_are_retained() -> None:
    package = normalize_strategic_human_evidence(
        {
            "functional_qa": {
                "statements": ["Checkout succeeded on the production-like environment."],
                "records": [{"scenario": "checkout", "status": "passed"}],
                "attachment_refs": ["evidence://qa/checkout-001"],
                "supplied_by": "QA lead",
                "captured_at": "2026-07-25T23:00:00Z",
            }
        }
    )

    qa = human_evidence_module(package, "functional_qa")
    assert package["status"] == "provided"
    assert package["provided_module_ids"] == ["functional_qa"]
    assert qa["status"] == "provided"
    assert qa["source_type"] == "mixed"
    assert qa["directly_scored"] is False
    assert qa["records"][0]["status"] == "passed"


def test_claimed_provided_status_without_content_fails_closed_to_not_assessed() -> None:
    package = normalize_strategic_human_evidence(
        {"stakeholder_context": {"status": "provided"}}
    )

    assert human_evidence_module(package, "stakeholder_context")["status"] == "not_assessed"
    assert package["status"] == "not_assessed"


def test_normalization_is_idempotent() -> None:
    first = normalize_strategic_human_evidence(
        {"accepted_risks": {"statements": ["Risk R-12 is accepted until Q4."]}}
    )
    second = normalize_strategic_human_evidence(first)

    assert first == second


def test_unknown_module_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown_human_evidence_module"):
        human_evidence_module({}, "invented_module")
