from __future__ import annotations

from nico.candidate_retained_triage_revalidation_v1 import (
    revalidate_retained_candidate_triage,
)


def _retained_dependency(**overrides):
    record = {
        "candidate_id": "candidate-dependency-1",
        "finding_id": "candidate-dependency-1",
        "category": "dependency",
        "scanner": "osv-scanner",
        "tool": "osv-scanner",
        "rule": "GHSA-example",
        "advisory": "GHSA-example",
        # Retain both the canonical projected fields and the scanner-native identity
        # consumed by fresh triage. This keeps the regression focused on reachability,
        # not on a synthetic missing-package fixture.
        "dependency_package": "example-package",
        "dependency_version": "1.0.0",
        "dependency_ecosystem": "PyPI",
        "package_name": "example-package",
        "installed_version": "1.0.0",
        "ecosystem": "PyPI",
        "manifest_path": "requirements.txt",
        "installed_version_affected": True,
        "scope": "production",
        "environment_relevant": True,
        "lineage_status": "carried_forward_exact",
        "previous_candidate_identity": "previous-candidate-dependency-1",
        "technical_triage_status": "complete",
        "technical_triage_verdict": "not_actionable",
        "technical_triage_confidence": 0.95,
        "technical_triage_rationale": "Historical recommendation.",
        "technical_triage_rationale_code": "tooling_transitive_no_supported_reachable_lock_path",
        "technical_triage_source": "retained_prior_nico_recommendation",
        "technical_triage_model_or_version": "prior-model",
        "technical_triage_proof_gaps": [],
        "proof_gaps": [],
        "reachability_assessment": "unknown",
        "technical_triage_reachability_assessment": "unknown",
        "human_review_required": True,
        "human_approval_status": "pending",
        "human_approval_carried_forward": False,
        "technical_triage_client_delivery_allowed": False,
        "occurrence_count": 1,
    }
    record.update(overrides)
    return record


def test_stale_retained_unknown_dependency_reachability_is_retriaged_fail_safe() -> None:
    register = {
        "findings": [_retained_dependency()],
        "technical_triage": {
            "status": "complete",
            "imported_candidate_count": 1,
            "workload_metrics": {},
        },
    }

    result = revalidate_retained_candidate_triage(register)
    candidate = result["findings"][0]
    triage = result["technical_triage"]
    revalidation = result["candidate_retained_triage_revalidation"]

    assert candidate["candidate_id"] == "candidate-dependency-1"
    assert candidate["technical_triage_source"].startswith("fresh_")
    assert candidate["technical_triage_verdict"] == "needs_review"
    assert "first_party_reachability" in candidate["technical_triage_proof_gaps"]
    assert candidate["retained_triage_revalidated_against_current_contract"] is True
    assert candidate["review_routing_class"] == "HUMAN_TECHNICAL_REVIEW"

    assert revalidation["revalidated_candidate_count"] == 1
    assert revalidation["candidate_counts_changed"] is False
    assert revalidation["scanner_evidence_changed"] is False
    assert revalidation["canonical_dispositions_changed"] is False
    assert revalidation["human_disposition_created"] is False
    assert revalidation["human_approval_created"] is False
    assert revalidation["client_delivery_allowed"] is False
    assert revalidation["score_effect"] == "none"

    assert triage["imported_candidate_count"] == 0
    assert triage["needs_review_count"] == 1
    assert triage["not_actionable_count"] == 0
    assert triage["technical_triage_completed"] == 1
    assert triage["technical_triage_pending"] == 0
    assert triage["technical_triage_coverage_pct"] == 100.0
    assert triage["human_disposition_created"] is False
    assert triage["reviewer_identity_created"] is False
    assert triage["human_approval_status"] == "pending"
    assert triage["client_delivery_allowed"] is False


def test_canonical_unaffected_dependency_resolution_is_not_retriaged_for_unknown_reachability() -> None:
    record = _retained_dependency(
        technical_triage_rationale_code="dependency_resolution_not_affected",
        technical_triage_rationale="Current resolved version is outside the affected advisory range.",
    )
    register = {
        "findings": [record],
        "technical_triage": {
            "status": "complete",
            "imported_candidate_count": 1,
            "workload_metrics": {},
        },
    }

    result = revalidate_retained_candidate_triage(register)
    candidate = result["findings"][0]

    assert candidate["technical_triage_source"] == "retained_prior_nico_recommendation"
    assert candidate["technical_triage_verdict"] == "not_actionable"
    assert "retained_triage_revalidated_against_current_contract" not in candidate
    assert result["candidate_retained_triage_revalidation"]["revalidated_candidate_count"] == 0


def test_explicit_reachability_proof_gap_remains_valid_retained_analysis() -> None:
    record = _retained_dependency(
        technical_triage_verdict="needs_review",
        technical_triage_proof_gaps=["first_party_reachability"],
        proof_gaps=["first_party_reachability"],
    )
    register = {
        "findings": [record],
        "technical_triage": {
            "status": "complete",
            "imported_candidate_count": 1,
            "workload_metrics": {},
        },
    }

    result = revalidate_retained_candidate_triage(register)
    candidate = result["findings"][0]

    assert candidate["technical_triage_source"] == "retained_prior_nico_recommendation"
    assert candidate["technical_triage_verdict"] == "needs_review"
    assert result["candidate_retained_triage_revalidation"]["revalidated_candidate_count"] == 0
