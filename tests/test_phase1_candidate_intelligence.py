from __future__ import annotations

from tests.phase1_candidate_fixtures import (
    SUBJECT, baseline_for, candidate, lineage_then_triage, register, retained_triage,
)

def test_new_candidate_receives_fresh_deterministic_triage() -> None:
    current = candidate("NEW", category="dependency", scanner="osv-scanner", rule="GHSA-1", path="requirements.lock", context={
        "scanned_package": {"name": "pillow", "version": "11.3.0", "ecosystem": "PyPI", "manifest_path": "requirements.lock"},
        "installed_version_affected": False,
        "dependency_scope": "production",
    })
    result = lineage_then_triage([current], [])
    finding = result["findings"][0]
    assert finding["lineage_status"] == "newly_observed"
    assert finding["technical_triage_status"] == "fresh_proposal"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["technical_triage_source"] == "fresh_deterministic_contextual_analysis"
    assert result["technical_triage"]["technical_triage_coverage_pct"] == 100.0


def test_evidence_changed_candidate_never_inherits_stale_reasoning() -> None:
    prior = candidate("OLD", evidence="old hit", line=10)
    current = candidate("CURRENT", evidence="changed evidence", line=11)
    source = retained_triage("OLD")
    result = lineage_then_triage([current], [prior], source_triage=source)
    finding = result["findings"][0]
    assert finding["lineage_status"] == "carried_forward_evidence_changed"
    assert finding["technical_triage_status"] == "fresh_proposal"
    assert finding["technical_triage_source"] != "retained_prior_nico_recommendation"
    assert finding["technical_triage_verdict"] == "needs_review"


def test_unchanged_candidate_can_retain_valid_prior_triage() -> None:
    prior = candidate("OLD")
    current = candidate("CURRENT")
    result = lineage_then_triage([current], [prior], source_triage=retained_triage("OLD"))
    finding = result["findings"][0]
    assert finding["lineage_status"] == "carried_forward_exact"
    assert finding["technical_triage_status"] == "imported_proposal"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["review_routing_class"] == "STABLE_CARRY_FORWARD"


def test_insufficient_evidence_fails_safe_to_needs_review() -> None:
    current = candidate("NEW", category="dependency", scanner="osv-scanner", rule="GHSA-X", context={})
    result = lineage_then_triage([current], [])
    finding = result["findings"][0]
    assert finding["technical_triage_verdict"] == "needs_review"
    assert "actual_scanned_package" in finding["proof_gaps"]
    assert finding["review_routing_class"] == "HUMAN_TECHNICAL_REVIEW"


def test_technical_verdict_never_becomes_human_disposition_or_approval() -> None:
    current = candidate("SECRET", category="secret", scanner="trufflehog", rule="aws", path="tests/fixture.env", severity="high", context={"verified": True, "synthetic": True, "scope": "test"})
    result = lineage_then_triage([current], [])
    finding = result["findings"][0]
    assert finding["technical_triage_verdict"] == "confirmed"
    assert finding["human_disposition"] == "pending"
    assert finding["human_approval_status"] == "pending"
    assert finding["technical_triage_client_delivery_allowed"] is False
    assert result["technical_triage"]["human_disposition_created"] is False
    assert result["technical_triage"]["client_delivery_allowed"] is False
