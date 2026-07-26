from __future__ import annotations

import pytest

from nico.strategic_human_evidence_v1 import (
    MODULES,
    decision_grade_stage_payload,
    human_evidence_module,
    normalize_strategic_human_evidence,
)


def test_missing_human_context_is_explicitly_not_assessed() -> None:
    package = normalize_strategic_human_evidence(None)

    assert package["status"] == "review_limited"
    assert package["complete_modules"] == []
    assert package["repository_inference_allowed"] is False
    assert package["status_counts"]["not_assessed"] == len(MODULES)
    assert len(package["human_evidence_sha256"]) == 64


def test_complete_functional_qa_matches_existing_decision_grade_schema() -> None:
    package = normalize_strategic_human_evidence(
        {
            "functional_qa": {
                "evidence": {
                    "test_cases": [{"scenario": "checkout", "expected": "success"}],
                    "observed_results": [{"scenario": "checkout", "actual": "success"}],
                },
                "reviewer": "QA lead",
                "observed_at": "2026-07-25T23:00:00Z",
                "source_reference": "evidence://qa/checkout-001",
            }
        }
    )

    qa = human_evidence_module(package, "functional_qa")
    assert qa["status"] == "complete"
    assert qa["assurance"] == "HUMAN EVIDENCE RETAINED · REVIEW REQUIRED"
    assert qa["directly_scored"] is False
    assert qa["evidence"]["observed_results"][0]["actual"] == "success"
    projected = decision_grade_stage_payload(package, ("functional_qa",))
    assert projected["functional_qa"]["reviewer"] == "QA lead"
    assert projected["functional_qa"]["test_cases"][0]["scenario"] == "checkout"


def test_incomplete_claim_fails_closed_to_partial() -> None:
    package = normalize_strategic_human_evidence(
        {
            "stakeholder_context": {
                "evidence": {"objectives": ["Launch by October"]},
                "reviewer": "Product owner",
            }
        }
    )

    module = human_evidence_module(package, "stakeholder_context")
    assert module["status"] == "partial"
    assert "constraints" in module["missing_fields"]
    assert "observed_at" in module["missing_metadata"]


def test_explicit_exclusion_requires_rationale() -> None:
    incomplete = normalize_strategic_human_evidence(
        {"platform_parity": {"excluded": True}}
    )
    complete = normalize_strategic_human_evidence(
        {
            "platform_parity": {
                "excluded": True,
                "exclusion_rationale": "The product has no browser or native client surface.",
            }
        }
    )

    assert human_evidence_module(incomplete, "platform_parity")["status"] == "partial"
    assert human_evidence_module(complete, "platform_parity")["status"] == "excluded"


def test_normalization_is_idempotent() -> None:
    first = normalize_strategic_human_evidence(
        {
            "accepted_risks": {
                "evidence": {"decisions": ["Risk R-12 is accepted until Q4."]},
                "reviewer": "CTO",
                "observed_at": "2026-07-25T23:05:00Z",
                "source_reference": "decision://R-12",
            }
        }
    )
    second = normalize_strategic_human_evidence(first)

    assert first == second


def test_unknown_module_is_rejected() -> None:
    with pytest.raises(KeyError, match="unknown_human_evidence_module"):
        human_evidence_module({}, "invented_module")
