from __future__ import annotations

from nico.decision_grade_consistency_v1 import (
    install_decision_grade_consistency_engine,
    validate_contract_consistency,
    wrap_contract_builder,
)
from nico.decision_grade_contract_v1 import (
    EvidenceStatus,
    ReadinessStatus,
    build_decision_grade_contract,
)

COMMIT = "a" * 40


def _record(index: int, *, priority: str = "P1", category: str = "architecture") -> dict[str, object]:
    return {
        "id": f"legacy-{index}",
        "priority": priority,
        "category": category,
        "title": f"Decision-grade risk {index}",
        "impact": "The unresolved condition can delay releases and increase engineering rework.",
        "confidence": "high",
        "evidence": f"cyclomatic_complexity={40 + index}",
        "location": f"src/module_{index}.py:{20 + index}",
        "recommendation": "Implement the bounded remediation and verify it on the validation commit.",
        "effort": "2-4 weeks",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": f"module_{index} cyclomatic complexity <= 30 and its workflow passes.",
        "release_blocker": priority == "P0",
    }


def _roadmap() -> list[dict[str, object]]:
    return [
        {
            "window": "0-30 days",
            "objective": "Close the highest-priority architecture risks.",
            "work_packages": [
                {
                    "title": "Decompose architecture hotspots",
                    "objective": "Reduce concentrated complexity while preserving behavior.",
                    "owner_role": "Product Engineering Architect",
                    "supporting_roles": [],
                    "effort": "2-4 weeks",
                    "dependencies": [],
                    "acceptance_criteria": [
                        "Target cyclomatic complexity <= 30",
                        "The production acceptance workflow passes on the remediation commit",
                    ],
                    "expected_impact": "Reduces release and regression exposure.",
                }
            ],
        }
    ]


def _assessment(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "technical_score": 75,
        "canonical_evidence_adjusted_score": 70,
        "maturity_signal": {
            "technical_score": 75,
            "score": 75,
            "evidence_adjusted_score": 70,
        },
        "findings_register": records,
        "sections": [],
        "scoring_weights": [
            {
                "control": "Architecture",
                "section_id": "architecture_debt",
                "weight": 1.0,
                "weight_percent": 100,
                "technical_score": 75,
                "weighted_contribution": 75.0,
                "assurance": "VERIFIED",
                "included": True,
            }
        ],
    }


def _contract(
    records: list[dict[str, object]] | None = None,
    *,
    stage_summaries: list[dict[str, object]] | None = None,
):
    source = records or [_record(1)]
    assessment = _assessment(source)
    contract = build_decision_grade_contract(
        identity={
            "run_id": "comprun_consistency_test",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "assessment_type": "comprehensive",
            "branch": "main",
            "nico_version": "0.1.1",
            "scanner_configuration_version": "test-v1",
        },
        assessment=assessment,
        stage_summaries=stage_summaries or [],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )
    return contract, assessment


def _codes(contract) -> set[str]:
    return {item.code for item in contract.validation_issues}


def test_valid_contract_reconciles_score_arithmetic() -> None:
    contract, assessment = _contract()
    validated, summary = validate_contract_consistency(contract, assessment)

    assert "technical_score_arithmetic_mismatch" not in _codes(validated)
    assert "weighted_contribution_mismatch" not in _codes(validated)
    assert summary["score_arithmetic"]["calculated_technical_score"] == 75
    assert summary["executive_risk_limit_met"] is True


def test_weighted_contribution_and_total_mismatch_block_delivery() -> None:
    contract, assessment = _contract()
    assessment["technical_score"] = 88
    assessment["scoring_weights"][0]["weighted_contribution"] = 10
    validated, _ = validate_contract_consistency(contract, assessment)

    assert validated.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
    assert "weighted_contribution_mismatch" in _codes(validated)
    assert "technical_score_arithmetic_mismatch" in _codes(validated)


def test_conflicting_evidence_commit_blocks_delivery() -> None:
    contract, assessment = _contract()
    contract.evidence_records[0].assessed_commit_sha = "b" * 40
    validated, _ = validate_contract_consistency(contract, assessment)

    assert validated.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
    assert "evidence_commit_mismatch" in _codes(validated)


def test_resolved_risk_is_removed_and_next_active_risk_is_promoted() -> None:
    records = [_record(index) for index in range(1, 9)]
    contract, assessment = _contract(records)
    first_id = contract.executive_risk_register[0]
    first = next(item for item in contract.findings if item.finding_id == first_id)
    first.current_status = "closed"
    validated, summary = validate_contract_consistency(contract, assessment)

    assert first_id not in validated.executive_risk_register
    assert len(validated.executive_risk_register) == 7
    assert summary["resolved_findings_excluded_from_executive_register"] is True
    assert "resolved_finding_removed_from_executive_register" in _codes(validated)


def test_release_approval_with_open_blocker_is_critical_contradiction() -> None:
    contract, assessment = _contract([_record(1, priority="P0")])
    contract.decision_postures.release.status = "approved"
    validated, _ = validate_contract_consistency(contract, assessment)

    assert validated.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
    assert "release_approved_with_open_blocker" in _codes(validated)


def test_required_scanner_failure_constrains_high_confidence_and_delivery() -> None:
    contract, assessment = _contract(
        [_record(1, category="static")],
        stage_summaries=[
            {
                "stage": "scanner_execution",
                "scanner_results": [
                    {
                        "tool": "semgrep",
                        "status": "failed",
                        "required": True,
                        "category": "static",
                        "reason": "worker unavailable",
                    }
                ],
            }
        ],
    )
    contract.decision_postures.client_delivery.status = "approved"
    validated, _ = validate_contract_consistency(contract, assessment)

    assert validated.scanner_executions[0].status == EvidenceStatus.FAILED
    assert "high_confidence_based_on_incomplete_scanner" in _codes(validated)
    assert "client_delivery_approved_with_required_evidence_incomplete" in _codes(validated)
    assert validated.readiness_status == ReadinessStatus.DELIVERY_BLOCKED


def test_roadmap_without_finding_and_owner_conflict_are_visible() -> None:
    contract, assessment = _contract()
    package = contract.roadmap_work_packages[0]
    package.related_finding_ids = []
    finding = contract.findings[0]
    package.owner_role = "Release Manager"
    package.supporting_roles = []
    validated, _ = validate_contract_consistency(contract, assessment)

    assert "roadmap_item_without_finding" in _codes(validated)
    assert "owner_assignment_conflict" in _codes(validated)


def test_swapped_technical_and_evidence_scores_are_detected() -> None:
    contract, assessment = _contract()
    assessment["technical_score"] = 70
    assessment["canonical_evidence_adjusted_score"] = 75
    assessment["maturity_signal"] = {
        "technical_score": 75,
        "score": 75,
        "evidence_adjusted_score": 70,
    }
    validated, _ = validate_contract_consistency(contract, assessment)

    assert "technical_and_evidence_scores_swapped" in _codes(validated)
    assert validated.readiness_status == ReadinessStatus.DELIVERY_BLOCKED


def test_wrapper_records_machine_readable_consistency_summary() -> None:
    assessment = _assessment([_record(1)])
    wrapped = wrap_contract_builder(build_decision_grade_contract)
    contract = wrapped(
        identity={
            "run_id": "comprun_consistency_wrapper",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "assessment_type": "comprehensive",
            "branch": "main",
            "nico_version": "0.1.1",
            "scanner_configuration_version": "test-v1",
        },
        assessment=assessment,
        stage_summaries=[],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
    )

    assert contract.executive_risk_register
    assert assessment["decision_grade_consistency"]["schema_version"] == "nico.decision_grade_consistency.v1"


def test_installer_is_idempotent() -> None:
    class ReportModule:
        build_decision_grade_contract = staticmethod(build_decision_grade_contract)

    first = install_decision_grade_consistency_engine(ReportModule)
    second = install_decision_grade_consistency_engine(ReportModule)

    assert first["bound"] is True
    assert second["bound"] is True
    assert second["client_ready_promoted_automatically"] is False
