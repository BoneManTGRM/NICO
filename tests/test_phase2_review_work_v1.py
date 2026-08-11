from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    _record_hash,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_review_work_record_v1 import apply_review_work_ledger
from nico.comprehensive_review_work_v1 import (
    apply_review_work_action,
    review_work_projection,
)


def _candidate(candidate_id: str, cluster_id: str, *, grouped: bool, severity: str = "low") -> dict:
    return {
        "candidate_id": candidate_id,
        "cluster_id": cluster_id,
        "cluster_size": 2 if grouped else 1,
        "cluster_candidate_ids": ["A", "B"] if grouped else [candidate_id],
        "representative_candidate_id": "A" if grouped else candidate_id,
        "grouped_review_eligible": grouped,
        "review_requires_individual_attention": not grouped,
        "homogeneous_evidence": True,
        "homogeneous_verdict": True,
        "review_unit_id": cluster_id if grouped else candidate_id,
        "review_routing_class": "CRITICAL_ATTENTION" if severity == "high" else "HUMAN_TECHNICAL_REVIEW",
        "severity": severity,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "human_disposition": None,
    }


def _register() -> dict:
    findings = [
        _candidate("A", "GROUP", grouped=True),
        _candidate("B", "GROUP", grouped=True),
        _candidate("C", "C", grouped=False, severity="high"),
    ]
    clusters = [
        {
            "cluster_id": "GROUP",
            "candidate_ids": ["A", "B"],
            "candidate_record_count": 2,
            "cluster_size": 2,
            "representative_candidate_id": "A",
            "grouped_review_eligible": True,
            "grouped_human_review_cluster": True,
            "homogeneous_evidence": True,
            "homogeneous_verdict": True,
            "underlying_candidate_disposition_required": True,
        },
        {
            "cluster_id": "C",
            "candidate_ids": ["C"],
            "candidate_record_count": 1,
            "cluster_size": 1,
            "representative_candidate_id": "C",
            "grouped_review_eligible": False,
            "grouped_human_review_cluster": False,
            "homogeneous_evidence": True,
            "homogeneous_verdict": True,
            "underlying_candidate_disposition_required": True,
        },
    ]
    return {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_record_count": 3,
        "findings": findings,
        "review_workload_clusters": clusters,
        "technical_triage": {
            "total_candidates": 3,
            "human_review_work_units": 2,
            "review_workload_clusters": clusters,
        },
    }


def _record(register: dict | None = None) -> dict:
    identity = {
        "run_id": "comprun_phase2_001",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_phase2_001",
        "customer_id": "customer_001",
        "project_id": "project_001",
        "assessment_depth": "strategic",
        "report_language": "en",
    }
    canonical = {
        "identity": {key: identity[key] for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")},
        "assessment": {"canonical_scanner_finding_register": register or _register()},
    }
    return {
        "identity": identity,
        "status": "review_required",
        "terminal": True,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_results": {
            "final_comprehensive_report_generation": {
                "report_package": {"json": canonical},
            }
        },
    }


def _human(action: str, reviewer: str = "Alice", role: str = "Security specialist", **extra) -> dict:
    return {
        "action": action,
        "reviewer": reviewer,
        "reviewer_role": role,
        "review_authorized": True,
        "authorization_confirmed": True,
        **extra,
    }


def _with_ledger(record: dict, ledger: dict) -> dict:
    return {**record, "review_work_ledger": deepcopy(ledger)}


def test_group_review_preserves_candidate_level_accounting_and_independent_qc() -> None:
    record = _record()
    t0 = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)

    ledger = apply_review_work_action(record, _human("start_session"), now=t0)
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "disposition_group",
            cluster_id="GROUP",
            disposition="false_positive",
            rationale="The retained evidence is a synthetic fixture and is not executable production code.",
        ),
        now=t0 + timedelta(minutes=5),
    )
    assert set(ledger["dispositions"]) == {"A", "B"}
    assert ledger["dispositions"]["A"]["group_action_id"] == ledger["dispositions"]["B"]["group_action_id"]
    assert ledger["dispositions"]["A"]["human_decision"] is True

    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "disposition_candidate",
            candidate_id="C",
            disposition="false_positive",
            rationale="The high-impact candidate is disproved by exact retained source context.",
            escalation_resolution="Escalation reviewed against the exact source and closed as a false positive.",
            escalation_owner="Alice",
        ),
        now=t0 + timedelta(minutes=10),
    )
    record = _with_ledger(record, ledger)

    with pytest.raises(ValueError, match="review_work_qc_requires_independent_reviewer"):
        apply_review_work_action(
            record,
            _human("quality_control", candidate_id="A", qc_outcome="agree", qc_note="same reviewer"),
            now=t0 + timedelta(minutes=20),
        )

    ledger = apply_review_work_action(
        record,
        _human(
            "quality_control",
            reviewer="Bob",
            role="Independent quality reviewer",
            candidate_id="A",
            qc_outcome="agree",
            qc_note="Independent evidence check agrees with the grouped human disposition.",
        ),
        now=t0 + timedelta(minutes=20),
    )
    projection = review_work_projection(_with_ledger(record, ledger))
    assert projection["dispositioned_candidate_count"] == 3
    assert projection["quality_control_required_count"] == 1
    assert projection["quality_control_completed_count"] == 1
    assert projection["unresolved_high_impact_candidate_ids"] == []
    assert projection["ready_for_final_approval"] is True
    assert projection["client_delivery_allowed"] is False


def test_evidence_requests_stakeholder_evidence_and_server_measured_four_hour_study() -> None:
    record = _record()
    t0 = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    ledger = apply_review_work_action(record, _human("start_session"), now=t0)
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "request_evidence",
            candidate_id="C",
            request_text="Provide production reachability proof.",
            owner="Engineering lead",
        ),
        now=t0 + timedelta(minutes=2),
    )
    request_id = ledger["evidence_requests"][0]["request_id"]
    projection = review_work_projection(_with_ledger(record, ledger))
    assert projection["open_evidence_request_count"] == 1
    assert projection["ready_for_final_approval"] is False

    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "resolve_evidence_request",
            request_id=request_id,
            resolution_note="Exact CI artifact and source path supplied.",
            evidence_references=["artifact://ci/reachability.json"],
        ),
        now=t0 + timedelta(minutes=8),
    )
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "stakeholder_evidence",
            statement="The component is not deployed in the production environment.",
            source_role="Product owner",
            evidence_reference="meeting://2026-08-11/product-owner",
        ),
        now=t0 + timedelta(minutes=9),
    )
    assert ledger["stakeholder_evidence"][0]["human_authored"] is True
    assert ledger["stakeholder_evidence"][0]["technical_score_unchanged"] is True

    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human("disposition_group", cluster_id="GROUP", disposition="false_positive", rationale="Synthetic grouped fixtures."),
        now=t0 + timedelta(minutes=15),
    )
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "disposition_candidate",
            candidate_id="C",
            disposition="not_applicable",
            rationale="Human evidence and retained deployment evidence establish non-production scope.",
            escalation_resolution="High-impact escalation closed after production-scope verification.",
            escalation_owner="Alice",
        ),
        now=t0 + timedelta(minutes=20),
    )
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "quality_control",
            reviewer="Bob",
            role="Independent quality reviewer",
            candidate_id="A",
            qc_outcome="agree",
            qc_note="Independent sample confirms the grouped evidence class.",
        ),
        now=t0 + timedelta(minutes=25),
    )
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(record, _human("stop_session"), now=t0 + timedelta(hours=1))
    assert ledger["review_sessions"][0]["duration_seconds"] == 3600

    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human("complete_empirical_study", reviewer="Bob", role="Independent quality reviewer"),
        now=t0 + timedelta(hours=1, minutes=1),
    )
    projection = review_work_projection(_with_ledger(record, ledger))
    measurement = projection["empirical_measurement"]
    assert measurement["status"] == "verified_within_four_hours"
    assert measurement["combined_specialist_seconds"] == 3600
    assert measurement["four_combined_specialist_hours_empirically_proven"] is True
    assert measurement["server_measured_only"] is True


def test_review_work_ledger_persists_inside_canonical_integrity_record() -> None:
    record = create_comprehensive_run_record(
        run_id="comprun_phase2_zero",
        repository="BoneManTGRM/NICO",
        commit_sha="f" * 40,
        evidence_ledger_id="ledger_phase2_zero",
        customer_id="customer_zero",
        project_id="project_zero",
        authorized=True,
    )
    register = {
        "candidate_record_count": 0,
        "findings": [],
        "review_workload_clusters": [],
        "technical_triage": {"human_review_work_units": 0},
    }
    canonical = {
        "identity": {
            "run_id": record["identity"]["run_id"],
            "repository": record["identity"]["repository"],
            "commit_sha": record["identity"]["commit_sha"],
            "evidence_ledger_id": record["identity"]["evidence_ledger_id"],
        },
        "assessment": {"canonical_scanner_finding_register": register},
    }
    record["completed_stages"] = list(COMPREHENSIVE_STAGES)
    record["progress_percent"] = 100.0
    record["status"] = "review_required"
    record["terminal"] = True
    record["stage_results"] = {
        "final_comprehensive_report_generation": {"report_package": {"json": canonical}}
    }
    record["integrity_sha256"] = _record_hash(record)
    assert validate_comprehensive_run_record(record)["status"] == "valid"

    ledger = apply_review_work_action(
        record,
        _human(
            "stakeholder_evidence",
            statement="No additional business evidence was required for this clean fixture.",
            source_role="Authorized reviewer",
        ),
        now=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
    )
    updated = apply_review_work_ledger(record, ledger=ledger)
    assert updated["revision"] == record["revision"] + 1
    assert updated["review_work_ledger"]["artifact_schema"] == "nico.comprehensive_review_work_ledger.v1"
    assert updated["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(updated)["status"] == "valid"
