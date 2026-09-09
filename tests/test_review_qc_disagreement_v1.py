"""Synthetic software acceptance only; no claim of professional independent review."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from nico import comprehensive_review_work_v1 as v1
from nico import comprehensive_review_work_v2 as v2
from tests.test_phase2_review_work_v1 import _candidate, _human, _record, _with_ledger

NOW = datetime(2026, 9, 9, 4, 0, tzinfo=UTC)


def record_for(module):
    candidate = _candidate("TEST-B101", "TEST-GROUP", grouped=False)
    candidate.update(technical_triage_verdict="not_actionable", technical_triage_confidence=0.95)
    # The smallest legacy QC group has two candidates; v2 explicit sampling needs one.
    cluster = {"cluster_id": "TEST-GROUP", "candidate_ids": ["TEST-B101"],
               "representative_candidate_id": "TEST-B101", "cluster_size": 1,
               "candidate_record_count": 1, "grouped_review_eligible": module is v1,
               "homogeneous_evidence": True, "homogeneous_verdict": True}
    candidate["grouped_review_eligible"] = module is v1
    register = {"candidate_record_count": 1, "findings": [candidate],
                "review_workload_clusters": [cluster]}
    if module is v1:
        partner = deepcopy(candidate)
        partner["candidate_id"] = "TEST-B101-PARTNER"
        register["findings"].append(partner)
        register["candidate_record_count"] = 2
        cluster.update(candidate_ids=["TEST-B101", "TEST-B101-PARTNER"], cluster_size=2, candidate_record_count=2)
    record = _record(register)
    if module is v1:
        record = change(record, module, "disposition_candidate", candidate_id="TEST-B101-PARTNER",
                        disposition="not_applicable", rationale="Second harmless grouped test assertion")
    if module is v2:
        record = change(record, module, "configure_qc_sampling", sample_size=1)
    assert module.review_work_projection(record)["quality_control_required_count"] == 1
    return record


def change(record, module, action, *, at=0, reviewer="TEST — Reviewer A", **fields):
    return _with_ledger(record, module.apply_review_work_action(
        record, _human(action, reviewer=reviewer, **fields), now=NOW + timedelta(seconds=at)))


def disposition(record, module, *, at=1, rationale="Harmless assertion in a test harness"):
    return change(record, module, "disposition_candidate", at=at, candidate_id="TEST-B101",
                  disposition="not_applicable", rationale=rationale)


def qc(record, module, outcome, *, at=2, reviewer="TEST — Independent QC B"):
    return change(record, module, "quality_control", at=at, reviewer=reviewer,
                  candidate_id="TEST-B101", qc_outcome=outcome,
                  qc_note="Synthetic QC rationale tied to the exact test assertion and current disposition")


@pytest.mark.parametrize("module", [v1, v2])
def test_disagreement_blocks_fully_dispositioned_run_until_new_independent_agreement(module):
    record = disposition(record_for(module), module)
    disagreed = qc(record, module, "disagree")
    before = deepcopy(disagreed)
    projection = module.review_work_projection(disagreed)
    assert projection["remaining_candidate_count"] == 0
    assert projection["quality_control_completed_count"] == 0
    assert projection["ready_for_final_approval"] is False
    with pytest.raises(ValueError, match="review_work_not_ready_for_approval"):
        module.assert_ready_for_approval(disagreed)
    assert disagreed == before
    resolved = qc(disagreed, module, "agree", at=3)
    assert module.assert_ready_for_approval(resolved)["ready_for_final_approval"] is True
    assert resolved["review_work_ledger"]["audit_events"][:-1] == before["review_work_ledger"]["audit_events"]
    assert [e["payload"]["qc_outcome"] for e in resolved["review_work_ledger"]["audit_events"]
            if e["action"] == "quality_control"] == ["disagree", "agree"]


@pytest.mark.parametrize("module", [v1, v2])
def test_changed_disposition_invalidates_agreement_without_erasing_qc_history(module):
    agreed = qc(disposition(record_for(module), module), module, "agree")
    assert module.assert_ready_for_approval(agreed)["ready_for_final_approval"] is True
    qc_before = deepcopy(agreed["review_work_ledger"]["quality_control"])
    changed = disposition(agreed, module, at=3, rationale="Corrected rationale: assertion checks arithmetic, not access control")
    assert changed["review_work_ledger"]["quality_control"] == qc_before
    projection = module.review_work_projection(changed)
    assert projection["quality_control_completed_count"] == 0
    assert projection["ready_for_final_approval"] is False
    with pytest.raises(ValueError, match="review_work_not_ready_for_approval"):
        module.assert_ready_for_approval(changed)
    renewed = qc(changed, module, "agree", at=4)
    assert module.assert_ready_for_approval(renewed)["ready_for_final_approval"] is True


@pytest.mark.parametrize("module", [v1, v2])
def test_qc_ordering_and_historical_unbound_records_fail_closed(module):
    record = record_for(module)
    with pytest.raises(ValueError, match="requires_candidate_disposition"):
        qc(record, module, "agree")
    record = disposition(record, module)
    with pytest.raises(ValueError, match="requires_independent_reviewer"):
        qc(record, module, "agree", reviewer="TEST — Reviewer A")
    record = qc(record, module, "agree")
    record["review_work_ledger"]["quality_control"]["TEST-B101"].pop("reviewed_disposition_sha256", None)
    before = deepcopy(record)
    assert module.review_work_projection(record)["ready_for_final_approval"] is False
    assert record == before


def test_resampling_cannot_discard_a_known_failed_or_stale_qc_obligation():
    for outcome in ("disagree", "agree"):
        record = qc(disposition(record_for(v2), v2), v2, outcome)
        if outcome == "agree":
            record = disposition(record, v2, at=3, rationale="Corrected after QC")
        record = change(record, v2, "configure_qc_sampling", at=4, sample_size=0)
        assert v2.review_work_projection(record)["ready_for_final_approval"] is False
        assert v2.review_work_projection(record)["quality_control_required_count"] == 1
        resolved = qc(record, v2, "agree", at=5)
        assert v2.assert_ready_for_approval(resolved)["ready_for_final_approval"] is True


@pytest.mark.parametrize("module", [v1, v2])
def test_unrelated_assignment_preserves_qc_and_audit_binds_server_observed_disposition(module):
    record = disposition(record_for(module), module)
    before = deepcopy(record["review_work_ledger"]["dispositions"]["TEST-B101"])
    record = change(record, module, "quality_control", at=2, reviewer="TEST — Independent QC B",
                    candidate_id="TEST-B101", qc_outcome="agree", qc_note="Exact assertion reviewed",
                    reviewed_disposition_sha256="forged-client-digest")
    event = record["review_work_ledger"]["audit_events"][-1]
    assert event["payload"]["reviewed_disposition"] == before
    assert event["payload"]["reviewed_disposition_sha256"] != "forged-client-digest"
    assert event["payload"]["reviewed_disposition_sha256"] == record["review_work_ledger"]["quality_control"]["TEST-B101"]["reviewed_disposition_sha256"]
    reassigned = change(record, module, "assign", at=3, target_id="TEST-B101",
                        assignee="TEST — Administrative Followup", specialist_role="Security specialist")
    assert module.assert_ready_for_approval(reassigned)["ready_for_final_approval"] is True
