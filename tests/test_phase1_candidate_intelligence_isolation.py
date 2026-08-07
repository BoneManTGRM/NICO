from __future__ import annotations

from nico.candidate_phase1_lineage_v1 import apply_subject_safe_lineage
from tests.phase1_candidate_fixtures import SUBJECT, baseline_for, candidate, lineage_then_triage, retained_triage, register


def test_cross_repository_identity_cannot_contaminate_lineage_or_triage() -> None:
    prior = candidate("OLD"); current = candidate("CURRENT"); other = {**SUBJECT, "repository": "OtherOrg/OtherRepo"}
    result = lineage_then_triage([current], [prior], source_triage=retained_triage("OLD"), subject=other)
    assert result["candidate_lineage"]["assessment_subject_match"] is False
    assert result["findings"][0]["lineage_status"] == "newly_observed"
    assert result["findings"][0]["technical_triage_source"] != "retained_prior_nico_recommendation"


def test_cross_project_identity_cannot_contaminate_lineage() -> None:
    prior = candidate("OLD"); current = candidate("CURRENT"); other = {**SUBJECT, "project_id": "other-project"}
    result = lineage_then_triage([current], [prior], subject=other)
    assert result["candidate_lineage"]["assessment_subject_match_reason"] == "assessment_subject_mismatch"
    assert result["candidate_lineage"]["carried_forward_total"] == 0


def test_cross_target_identity_cannot_contaminate_lineage() -> None:
    prior = candidate("OLD"); current = candidate("CURRENT"); other = {**SUBJECT, "assessment_target_id": "subdir"}
    result = lineage_then_triage([current], [prior], subject=other)
    assert result["findings"][0]["lineage_status"] == "newly_observed"


def test_unscoped_current_identity_fails_closed() -> None:
    prior = candidate("OLD"); current = candidate("CURRENT")
    lined = apply_subject_safe_lineage({"findings": [current], "totals": {"raw": 1}}, baseline=baseline_for([prior]))
    assert lined["candidate_lineage"]["assessment_subject_match"] is False
    assert lined["candidate_lineage"]["assessment_subject_match_reason"] == "current_subject_identity_missing"
    assert lined["findings"][0]["lineage_status"] == "newly_observed"


def test_cross_run_candidate_id_cannot_import_retained_triage_without_safe_lineage() -> None:
    from nico.candidate_phase1_triage_v1 import apply_phase1_technical_triage
    current = candidate("CURRENT-RUN"); current["prior_candidate_id"] = "OLD-OTHER-RUN"; current["lineage_status"] = "newly_observed"
    result = apply_phase1_technical_triage(register([current]), triage=retained_triage("OLD-OTHER-RUN"))
    finding = result["findings"][0]
    assert result["technical_triage"]["imported_candidate_count"] == 0
    assert finding["technical_triage_status"] == "fresh_proposal"
    assert finding["technical_triage_source"] == "fresh_deterministic_contextual_analysis"
