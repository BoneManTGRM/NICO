from __future__ import annotations

from nico import comprehensive_final_artifact_truth_v53 as artifact_truth
from nico.comprehensive_blocked_run_recovery_v1 import (
    final_artifact_recovery_stage,
    rewind_blocked_run_for_final_artifact_recovery,
)
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_report_package import _stage_summary
from nico.comprehensive_run_record import (
    _record_hash,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.phase3_planning_synthesis_v1 import executive_briefing_provider


def _phase3_context() -> dict:
    assessment = {
        "technical_score": 93,
        "evidence_adjusted_score": 93,
        "canonical_evidence_adjusted_score": 93,
        "maturity_signal": {
            "level": "Exceptional",
            "score": 93,
            "presented_score": 93,
            "technical_score": 93,
            "evidence_adjusted_score": 93,
            "canonical_evidence_adjusted_score": 93,
        },
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "presented_score": 78,
                "summary": "Exact-source hotspots require sequencing.",
            },
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "presented_score": 100,
                "summary": "Configuration maturity is strong.",
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "presented_score": 96,
                "summary": "Dependency evidence remains review-gated.",
            },
        ],
    }
    return {
        "run_id": "comprun_phase3_score_scope",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_phase3_score_scope",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "prior_stage_results": {
            "evidence_reconciliation_and_scoring": {"assessment": assessment},
            "six_month_roadmap": {"roadmap": []},
            "staffing_sequencing_and_cost": {"staffing_plan": []},
        },
    }


def test_phase3_priority_section_scores_do_not_masquerade_as_canonical_stage_score() -> None:
    context = _phase3_context()
    result = executive_briefing_provider(context)
    briefing = result["executive_briefing"]

    assert briefing["technical_score"] == 93
    assert briefing["top_technical_priorities"][0]["section_score"] == 78
    assert briefing["top_technical_priorities"][0]["score_scope"] == "canonical_section"
    assert "technical_score" not in briefing["top_technical_priorities"][0]

    summary = _stage_summary("risk_reduction_and_executive_briefing", result)
    rendered = "\n".join(summary["evidence"])
    assert "technical_score: 93" in rendered
    assert "top_technical_priorities[0].section_score: 78" in rendered
    assert "top_technical_priorities[0].technical_score" not in rendered

    canonical = {
        "assessment": context["prior_stage_results"]["evidence_reconciliation_and_scoring"]["assessment"],
        "stage_summaries": [summary],
    }
    assert artifact_truth._score_stage_consistent(canonical) is True


def _blocked_stage_score_record() -> dict:
    record = create_comprehensive_run_record(
        run_id="comprun_phase3_score_scope_recovery",
        repository="BoneManTGRM/NICO",
        commit_sha="b" * 40,
        evidence_ledger_id="ledger_phase3_score_scope_recovery",
        customer_id="default_customer",
        project_id="default_project",
        authorized=True,
    )
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == "cross_format_truth_verification":
            result = {
                "status": "blocked",
                "reason": "final_artifact_truth_verification_failed",
                "failed_checks": ["stage_score_evidence_matches_canonical"],
                "final_artifact_truth": {
                    "status": "blocked",
                    "failed_checks": ["stage_score_evidence_matches_canonical"],
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        else:
            result = {
                "status": "complete",
                "evidence": {"stage": stage_id},
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        record = apply_comprehensive_stage_result(record, stage_id=stage_id, result=result)
        if stage_id == "cross_format_truth_verification":
            break
    return record


def test_legacy_v4_blocked_run_gets_one_semantic_repair_from_executive_briefing() -> None:
    blocked = _blocked_stage_score_record()
    blocked["recovery_history"] = [
        {
            "artifact_schema": "nico.comprehensive_blocked_run_recovery.v4",
            "source_failed_stage": "cross_format_truth_verification",
            "source_reason": "final_artifact_truth_verification_failed",
            "source_failed_checks": ["stage_score_evidence_matches_canonical"],
            "rerun_from_stage": "final_comprehensive_report_generation",
            "recovery_scope": "final_report_only",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    ]
    blocked["integrity_sha256"] = _record_hash(blocked)
    assert validate_comprehensive_run_record(blocked)["status"] == "valid"
    assert final_artifact_recovery_stage(blocked) == "risk_reduction_and_executive_briefing"

    recovered = rewind_blocked_run_for_final_artifact_recovery(blocked)

    target_index = COMPREHENSIVE_STAGES.index("risk_reduction_and_executive_briefing")
    assert recovered["status"] == "running"
    assert recovered["terminal"] is False
    assert recovered["completed_stages"] == list(COMPREHENSIVE_STAGES[:target_index])
    assert recovered["progress_percent"] == round(
        (target_index / len(COMPREHENSIVE_STAGES)) * 100,
        2,
    )
    assert len(recovered["recovery_history"]) == 2
    assert recovered["recovery_history"][-1]["rerun_from_stage"] == (
        "risk_reduction_and_executive_briefing"
    )
    assert recovered["recovery_history"][-1]["recovery_scope"] == (
        "executive_briefing_and_downstream"
    )
    assert recovered["recovery_history"][-1]["recovery_budget_scope"] == (
        "source_failed_stage"
    )
    assert validate_comprehensive_run_record(recovered)["status"] == "valid"
