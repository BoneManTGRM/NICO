from __future__ import annotations

import pytest
from pydantic import ValidationError

from nico.decision_grade_contract_v1 import build_decision_grade_contract
from nico.decision_grade_findings_v1 import Finding, RoadmapWorkPackage, rank_executive_findings
from nico.decision_grade_readiness_v1 import DecisionGradeAssessment, validate_report_readiness
from nico.decision_grade_types_v1 import (
    AcceptanceCriterion, AssessmentIdentity, CostMode, CostOfInaction,
    DeliveryStatus, EvidenceLocation, EvidenceRecord, EvidenceStatus,
    HumanApproval, RenderValidation, ResidualRisk, ScannerExecutionRecord,
    ScoreControl, TimeWindow, WorkClassification,
)

SHA = "a" * 40


def criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        criterion_id="AC-001", description="The CI workflow passes on the validation commit.",
        validation_method="workflow status", target_commit_sha=SHA,
        workflow_name="CI", passed=True,
    )


def finding(fid: str = "RISK-P1-001") -> Finding:
    return Finding(
        finding_id=fid, title="CI reliability is below threshold", priority="P1",
        severity="high", likelihood="likely", business_criticality="high",
        confidence="high", finding_type="ci_reliability", scope="github-actions/CI",
        evidence_ids=["E-001"], factual_statement="Retained history contains recurrent failures.",
        technical_interpretation="Release verification is not consistently reproducible.",
        business_impact="Releases may be delayed and engineering time may be lost.",
        decision_areas=["release", "operations"], recommended_action="Repair recurrent causes.",
        owner_role="Platform Engineer", effort="M", expected_impact="Predictable releases.",
        acceptance_criteria=[criterion()],
        cost_of_inaction=CostOfInaction(mode=CostMode.QUALITATIVE, time_window_days=90, qualitative_exposure="Material"),
        residual_risk=ResidualRisk(
            reduced_risk="Recurring failures are removed.", not_eliminated="Provider outages remain possible.",
            remaining_likelihood="unlikely", remaining_impact="A release may be delayed.",
        ),
        roadmap_work_package_ids=["WP-001"], backlog_item_ids=["BACKLOG-001"],
    )


def ready_package() -> DecisionGradeAssessment:
    return DecisionGradeAssessment(
        identity=AssessmentIdentity(assessment_id="run-1", assessment_type="comprehensive", repository="BoneManTGRM/NICO", commit_sha=SHA),
        technical_score=80, evidence_adjusted_score=76,
        score_controls=[ScoreControl(control_id="ci", raw_score=80, weight=1, contribution=80, evidence_status="complete")],
        evidence_records=[EvidenceRecord(evidence_id="E-001", category="ci", collector="github-actions", status="complete", commit_sha=SHA, location=EvidenceLocation(control_name="CI"))],
        findings=[finding()], executive_risk_ids=["RISK-P1-001"],
        roadmap=[RoadmapWorkPackage(
            work_package_id="WP-001", title="Stabilize CI", time_window=TimeWindow.DAYS_0_30,
            related_finding_ids=["RISK-P1-001"], objective="Remove recurrent failures.",
            implementation_steps=["Classify failures.", "Repair recurrent causes."], owner_role="Platform Engineer",
            effort_range="M", classification=WorkClassification.QUICK_WIN,
            expected_technical_impact="Reliable verification.", expected_business_impact="Lower release delay.",
            acceptance_criteria_ids=["AC-001"], residual_risk="Provider outages remain possible.",
            sequencing_rationale="Release evidence must be reliable first.",
        )],
        scanners=[ScannerExecutionRecord(scanner_name="github-actions", status="complete")],
        scope_boundaries=["Production runtime behavior was not assessed."],
        render_validation=RenderValidation(pdf_rendered=True, markdown_rendered=True, json_rendered=True, backlog_export_rendered=True, executive_brief_pages=1),
        human_approval=HumanApproval(required=True, approved=True, reviewer="Reviewer", approved_artifact_digest="digest"),
        report_artifact_digest="digest",
    )


def test_acceptance_criteria_require_durable_anchor() -> None:
    with pytest.raises(ValidationError):
        AcceptanceCriterion(criterion_id="AC-X", description="Implementation is independently verified.", validation_method="review")


def test_monetary_estimates_require_assumptions() -> None:
    with pytest.raises(ValidationError):
        CostOfInaction(mode="scenario", time_window_days=90, currency="USD", amount_low=1000, amount_base=2000, amount_high=3000)


def test_fingerprint_is_stable_across_report_wording() -> None:
    first = finding()
    second = first.model_copy(update={"title": "Different wording"})
    assert first.fingerprint(ready_package().evidence_records) == second.fingerprint(ready_package().evidence_records)


def test_executive_ranking_is_deterministic_and_capped() -> None:
    ranked = rank_executive_findings(reversed([finding(f"RISK-P1-{i:03d}") for i in range(1, 10)]))
    assert [item.finding_id for item in ranked] == [f"RISK-P1-{i:03d}" for i in range(1, 8)]


def test_all_gates_can_earn_client_ready() -> None:
    result = validate_report_readiness(ready_package())
    assert result.delivery_status == DeliveryStatus.CLIENT_READY.value
    assert result.issues == []


def test_failed_required_scanner_is_evidence_incomplete() -> None:
    package = ready_package().model_copy(update={"scanners": [ScannerExecutionRecord(scanner_name="semgrep", status=EvidenceStatus.FAILED)]})
    result = validate_report_readiness(package)
    assert result.delivery_status == DeliveryStatus.EVIDENCE_INCOMPLETE.value


def test_commit_mismatch_blocks_delivery() -> None:
    bad = ready_package().evidence_records[0].model_copy(update={"commit_sha": "b" * 40})
    result = validate_report_readiness(ready_package().model_copy(update={"evidence_records": [bad]}))
    assert result.delivery_status == DeliveryStatus.DELIVERY_BLOCKED.value


def test_p1_requires_complete_traceability() -> None:
    incomplete = finding().model_copy(update={"acceptance_criteria": [], "roadmap_work_package_ids": [], "backlog_item_ids": [], "residual_risk": None})
    result = validate_report_readiness(ready_package().model_copy(update={"findings": [incomplete], "roadmap": []}))
    codes = {item.code for item in result.issues}
    assert {"p1_missing_acceptance_criteria", "p1_missing_roadmap_mapping", "p1_missing_backlog_mapping", "p1_missing_residual_risk"} <= codes


def test_unsupported_benchmark_blocks_delivery() -> None:
    risky = finding().model_copy(update={"benchmark_claim": "This is in the highest-risk quartile."})
    result = validate_report_readiness(ready_package().model_copy(update={"findings": [risky]}))
    assert result.delivery_status == DeliveryStatus.DELIVERY_BLOCKED.value


def test_approval_must_match_exact_artifact() -> None:
    package = ready_package().model_copy(update={"human_approval": HumanApproval(required=True, approved=True, reviewer="Reviewer", approved_artifact_digest="other")})
    result = validate_report_readiness(package)
    assert result.delivery_status == DeliveryStatus.DELIVERY_BLOCKED.value


def test_builder_is_deterministic_and_fails_closed() -> None:
    payload = {"repository": "BoneManTGRM/NICO", "commit_sha": SHA, "run_id": "run-1", "assessment_type": "comprehensive"}
    first = build_decision_grade_contract(payload)
    second = build_decision_grade_contract(dict(reversed(list(payload.items()))))
    assert first["readiness"]["fingerprint"] == second["readiness"]["fingerprint"]
    assert first["readiness"]["delivery_status"] == DeliveryStatus.HUMAN_REVIEW_REQUIRED.value


def test_acceptance_criterion_must_target_package_commit() -> None:
    bad = criterion().model_copy(update={"target_commit_sha": "b" * 40})
    risky = finding().model_copy(update={"acceptance_criteria": [bad]})
    result = validate_report_readiness(ready_package().model_copy(update={"findings": [risky]}))
    assert result.delivery_status == DeliveryStatus.DELIVERY_BLOCKED.value
    assert "acceptance_commit_sha_mismatch" in {item.code for item in result.issues}


def test_approved_package_requires_artifact_digest() -> None:
    package = ready_package().model_copy(update={"report_artifact_digest": None})
    result = validate_report_readiness(package)
    assert result.delivery_status == DeliveryStatus.DELIVERY_BLOCKED.value
    assert "report_artifact_digest_missing" in {item.code for item in result.issues}


def test_evidence_adjusted_score_cannot_exceed_technical_score() -> None:
    package = ready_package().model_copy(update={"evidence_adjusted_score": 90})
    result = validate_report_readiness(package)
    assert result.delivery_status == DeliveryStatus.DELIVERY_BLOCKED.value
