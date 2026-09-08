from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from nico import comprehensive_canonical_report_source_v1 as source
from nico.comprehensive_finding_roadmap_v1 import bind_final_finding_roadmap


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


def _context(locale="en"):
    return {
        "run_id": "comprun_roadmap_regression",
        "repository": "internal-fixture/authorized-scope",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_roadmap_regression",
        "customer_id": "synthetic_customer",
        "project_id": "synthetic_project",
        "generated_at": "2026-09-08T20:00:00Z",
        "report_language": locale,
        "prior_stage_results": {
            "repository_and_delivery_evidence": {
                "status": "complete",
                "complexity_evidence": {"hotspots": [{
                    "path": "nico/report.py", "line": 40, "end_line": 140,
                    "name": "build_report", "cyclomatic_complexity": 61, "method": "python_ast",
                }]},
            },
            "six_month_roadmap": {
                "status": "complete", "summary": "Stage evidence was recorded.",
                "roadmap": [{"window": "91-180 days", "objective": "Invented generic work must disappear."}],
            },
            "staffing_sequencing_and_cost": {
                "status": "complete", "summary": "Stage evidence was recorded.",
                "staffing_plan": [{"role_category": "Generic role", "effort_band": "medium_to_large"}],
            },
        },
    }


def _canonical():
    return {
        "identity": {key: value for key, value in _context().items() if key in {"run_id", "repository", "commit_sha", "evidence_ledger_id"}},
        "report_language": "en",
        "assessment": {},
        "canonical_findings": [
            {"finding_id": "F-1", "status": "review_required", "disposition": "unconfirmed", "severity": "high", "source_commit_sha": "a" * 40, "location": "src/a.py:7", "recommendation": "Add an authorization check.", "verification": ["The denied request returns 403."], "impact": "A denied request reaches a private resource."},
            {"finding_id": "F-2", "status": "confirmed", "disposition": "confirmed", "severity": "medium", "source_commit_sha": "a" * 40, "location": "src/b.py:8", "recommendation": "Validate this input.", "verification": ["Rejected input reaches its restricted state."]},
        ],
        "stage_summaries": [{"stage_id": "six_month_roadmap"}, {"stage_id": "staffing_sequencing_and_cost"}],
        "review_candidate_summary": {"review_required_total": 3},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _assert_bound_report(result):
    assert result["status"] == "complete"
    canonical = result["canonical_report"]
    assert canonical.get("roadmap"), "final roadmap is not bound to restored findings"
    finding = canonical["canonical_findings"][0]
    package = next(item for item in canonical["roadmap"] if item["kind"] == "finding_review_and_remediation")
    assert package["finding_id"] == finding["finding_id"]
    assert package["source_refs"][0]["record_sha256"] == _hash(finding)
    assert package["retained_correction"] == finding["recommendation"]
    assert package["retained_verification"] == finding["verification"]
    assert package["source_binding"]["commit_sha"] == "a" * 40
    assert package["source_binding"]["run_id"] == _context()["run_id"]
    assert result["canonical_truth_sha256"] == source._canonical_hash(canonical)
    assert result["report_package"]["json"] == canonical
    stage = next(row for row in canonical["stage_summaries"] if row["stage_id"] == "six_month_roadmap")
    assert package["package_id"] in "\n".join(stage["evidence"])
    assert "Invented generic work" not in json.dumps(stage)
    assert canonical["human_review_required"] is True
    assert canonical["client_delivery_allowed"] is False
    return canonical


@pytest.mark.parametrize("locale", ["en", "es-MX"])
def test_actual_canonical_builder_binds_late_restored_findings_before_hashing(locale):
    context = _context(locale)
    before = deepcopy(context)
    canonical = _assert_bound_report(source.build_canonical_report_source(context))
    assert context == before
    assert canonical["roadmap_truth"]["binding_boundary"] == "after_final_canonical_finding_reconciliation"
    assert canonical["roadmap"][0]["retained_disposition"] != "confirmed"
    assert canonical["roadmap_truth"]["approved_dates_present"] is False
    if locale == "es-MX":
        stage = next(row for row in canonical["stage_summaries"] if row["stage_id"] == "six_month_roadmap")
        assert "provisionales" in stage["summary"]
        assert "Validar el hallazgo" in "\n".join(stage["evidence"])


def test_actual_builder_negative_control_rejects_the_original_unbound_path(monkeypatch):
    monkeypatch.setattr(source, "bind_final_finding_roadmap", lambda canonical, **kwargs: {**canonical, "roadmap": [], "roadmap_truth": {}})
    with pytest.raises(AssertionError, match="final roadmap is not bound"):
        _assert_bound_report(source.build_canonical_report_source(_context()))


def test_packages_preserve_dispositions_and_candidates_never_become_confirmed_defects():
    original = _canonical()
    before = deepcopy(original)
    report = bind_final_finding_roadmap(original, raw_stages={})
    assert original == before
    by_finding = {row["finding_id"]: row for row in report["roadmap"] if "finding_id" in row}
    assert by_finding["F-1"]["retained_disposition"] == "unconfirmed"
    assert by_finding["F-2"]["retained_disposition"] == "confirmed"
    review = next(row for row in report["roadmap"] if row["kind"] == "candidate_disposition")
    assert review["review_required_candidate_count"] == 3
    assert "finding_id" not in review
    assert report["canonical_findings"] == original["canonical_findings"]
    for row in report["roadmap"]:
        assert row["sequence_state"] == "nico_proposed"
        assert row["execution_state"] == "not_started"
        assert row["stakeholder_approved"] is False
        assert row["assigned_owner"] is None
        assert row["committed_date"] is None
        assert row["capacity_estimate"] is None
        assert row["cost_estimate"] is None


@pytest.mark.parametrize("field,value", [("source_commit_sha", "b" * 40), ("run_id", "another-run"), ("repository", "another/repository")])
def test_wrong_source_findings_cannot_acquire_a_bound_remediation_package(field, value):
    canonical = _canonical()
    canonical["canonical_findings"][0][field] = value
    report = bind_final_finding_roadmap(canonical, raw_stages={})
    assert all(row.get("finding_id") != "F-1" for row in report["roadmap"])
    assert report["roadmap_truth"]["omitted_finding_refs"][0]["finding_id"] == "F-1"
    assert report["canonical_findings"][0][field] == value


@pytest.mark.parametrize("state", ["excluded", "resolved", "false_positive", "not_applicable", "accepted_risk"])
def test_closed_or_excluded_disposition_does_not_manufacture_remediation(state):
    canonical = _canonical()
    canonical["canonical_findings"][0]["disposition"] = state
    report = bind_final_finding_roadmap(canonical, raw_stages={})
    assert all(row.get("finding_id") != "F-1" for row in report["roadmap"])
    assert report["canonical_findings"][0]["disposition"] == state


def test_explicit_evidence_gaps_are_linked_deduplicated_and_exclusions_preserved():
    gap = {"evidence_type": "runtime_functional_qa", "state": "not_supplied", "why_it_matters": "Runtime behavior is unverified.", "evidence_to_resolve": "Retain the authorized runtime observations."}
    stages = {
        "functional_qa": {"status": "complete", "missing_evidence": [gap]},
        "risk_reduction_and_executive_briefing": {"status": "complete", "missing_evidence": [deepcopy(gap)]},
        "excluded_stage": {"status": "excluded", "missing_evidence": [{**gap, "evidence_type": "excluded_input"}]},
        "requirements_traceability": {"status": "complete", "missing_evidence": [{**gap, "state": "excluded", "evidence_type": "excluded_requirements"}]},
    }
    canonical = _canonical()
    report = bind_final_finding_roadmap(canonical, raw_stages=stages)
    gaps = [row for row in report["roadmap"] if row["kind"] == "evidence_gap_resolution"]
    assert len(gaps) == 1
    assert gaps[0]["evidence_type"] == "runtime_functional_qa"
    assert len(gaps[0]["source_refs"]) == 2
    assert all(ref["record_sha256"] == _hash(gap) for ref in gaps[0]["source_refs"])
    assert "finding_id" not in gaps[0]
    assert report["canonical_findings"] == canonical["canonical_findings"]
    reversed_canonical = deepcopy(canonical)
    reversed_canonical["canonical_findings"].reverse()
    reordered = bind_final_finding_roadmap(reversed_canonical, raw_stages=dict(reversed(list(stages.items()))))
    assert reordered["roadmap"] == report["roadmap"]
    assert reordered["roadmap_truth"] == report["roadmap_truth"]


def test_empty_evidence_does_not_fill_six_months_with_invented_work():
    canonical = _canonical()
    canonical["canonical_findings"] = []
    canonical["review_candidate_summary"] = {}
    report = bind_final_finding_roadmap(canonical, raw_stages={"scoring": {"assessment": {"sections": [{"presented_score": 1}]}}})
    assert report["roadmap"] == []
    assert report["roadmap_truth"]["work_package_count"] == 0
    assert report["roadmap_truth"]["illustrative_windows"] == ["0-30 days", "31-90 days", "91-180 days"]
    assert report["roadmap_truth"]["windows_are_commitments"] is False
    assert report["stage_summaries"][1]["suggested_role_types"] == []


def test_materially_changed_finding_changes_package_and_report_identity_without_approval():
    context = _context()
    before = source.build_canonical_report_source(context)
    changed = deepcopy(context)
    changed["prior_stage_results"]["repository_and_delivery_evidence"]["complexity_evidence"]["hotspots"][0]["cyclomatic_complexity"] = 74
    after = source.build_canonical_report_source(changed)
    assert before["report_id"] != after["report_id"]
    assert before["canonical_truth_sha256"] != after["canonical_truth_sha256"]
    assert before["canonical_report"]["roadmap"][0]["package_id"] != after["canonical_report"]["roadmap"][0]["package_id"]
    assert after["human_review_required"] is True
    assert after["client_delivery_allowed"] is False


def test_actual_canonical_builder_binds_retained_gap_records():
    context = _context()
    gap = {"evidence_type": "runtime_functional_qa", "state": "not_supplied", "why_it_matters": "Runtime behavior is unverified.", "evidence_to_resolve": "Retain the authorized runtime observations."}
    context["prior_stage_results"]["functional_qa"] = {"status": "complete", "missing_evidence": [gap]}
    result = source.build_canonical_report_source(context)
    package = next(row for row in result["canonical_report"]["roadmap"] if row["kind"] == "evidence_gap_resolution")
    assert package["source_refs"] == [{"surface": "prior_stage_results", "stage_id": "functional_qa", "field": "missing_evidence", "evidence_type": "runtime_functional_qa", "record_sha256": _hash(gap)}]
    assert package["retained_required_input"] == gap["evidence_to_resolve"]
    assert result["canonical_truth_sha256"] == source._canonical_hash(result["canonical_report"])


@pytest.mark.parametrize("wrong_layer", ["stage", "gap"])
def test_wrong_run_gap_or_parent_cannot_acquire_current_report_binding(wrong_layer):
    gap = {"evidence_type": "runtime_functional_qa", "state": "not_supplied", "evidence_to_resolve": "Retain runtime observations."}
    stage = {"status": "complete", "missing_evidence": [gap]}
    (stage if wrong_layer == "stage" else gap)["run_id"] = "unrelated-run"
    result = bind_final_finding_roadmap(_canonical(), raw_stages={"functional_qa": stage})
    assert not any(row["kind"] == "evidence_gap_resolution" for row in result["roadmap"])
    assert result["roadmap_truth"]["omitted_gap_refs"][0]["reason"] == "gap_source_identity_mismatch"
