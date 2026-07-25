from __future__ import annotations

import pytest
from pydantic import ValidationError

from nico.decision_grade_contract_v1 import (
    AcceptanceCriterion,
    CostOfInaction,
    EvidenceStatus,
    Priority,
    ReadinessStatus,
    build_decision_grade_contract,
    contract_quality_summary,
    stable_finding_id,
)


COMMIT = "a" * 40


def _identity() -> dict[str, object]:
    return {
        "run_id": "comprun_contract_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "assessment_type": "comprehensive",
        "branch": "main",
        "nico_version": "0.1.1",
        "scanner_configuration_version": "test-v1",
    }


def _record(index: int, *, priority: str = "P1", category: str = "architecture") -> dict[str, object]:
    return {
        "id": f"legacy-{index}",
        "priority": priority,
        "category": category,
        "title": f"Complexity hotspot {index}",
        "impact": "Concentrated logic increases regression risk and review cost.",
        "confidence": "high",
        "evidence": f"cyclomatic_complexity={40 + index}; method=typescript-ast",
        "location": f"apps/web/app/assessment/component{index}.tsx:{10 + index}",
        "recommendation": "Decompose the hotspot and preserve behavior with characterization tests.",
        "effort": "2-4 weeks",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": f"component{index} cyclomatic complexity <= 30 and its workflow passes on the validation commit.",
    }


def _roadmap() -> list[dict[str, object]]:
    return [
        {
            "window": "0-30 days",
            "objective": "Close the highest-priority verified risks first.",
            "work_packages": [
                {
                    "title": "Decompose the highest-complexity hotspots",
                    "objective": "Reduce concentrated complexity while preserving behavior.",
                    "owner_role": "Product Engineering Architect",
                    "effort": "2-4 weeks",
                    "dependencies": ["Named hotspot register", "Characterization tests"],
                    "acceptance_criteria": [
                        "Target cyclomatic complexity <= 30",
                        "The production acceptance workflow passes on the remediation commit",
                    ],
                    "expected_impact": "Reduces regression probability and review cost.",
                }
            ],
        }
    ]


def _assessment(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "technical_score": 82,
        "canonical_evidence_adjusted_score": 78,
        "findings_register": records,
        "sections": [],
        "scoring_weights": [],
    }


def test_stable_finding_id_ignores_line_number_changes() -> None:
    first = _record(1)
    second = dict(first)
    second["location"] = "apps/web/app/assessment/component1.tsx:999"
    assert stable_finding_id(first) == stable_finding_id(second)


def test_acceptance_criterion_requires_durable_anchor_and_evidence() -> None:
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            criterion_id="AC-1",
            description="The change passes.",
            validation_method="exact_sha_rerun",
            target_commit_sha=COMMIT,
            required_evidence=[],
        )


def test_monetary_cost_of_inaction_requires_assumptions() -> None:
    with pytest.raises(ValidationError):
        CostOfInaction(
            mode="scenario",
            categories=["release_delay"],
            timeframe_days=90,
            amount_low=1000,
            amount_high=5000,
            currency="USD",
            assumptions=[],
            confidence="low",
            rationale="Scenario only.",
        )


def test_contract_caps_executive_register_and_completes_p1_traceability() -> None:
    records = [_record(index) for index in range(1, 10)]
    contract = build_decision_grade_contract(
        identity=_identity(),
        assessment=_assessment(records),
        stage_summaries=[],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )
    summary = contract_quality_summary(contract)

    assert len(contract.findings) == 9
    assert len(contract.executive_risk_register) == 7
    assert summary["executive_risk_limit_met"] is True
    assert summary["p0_p1_traceability_complete"] is True
    assert all(finding.roadmap_mappings for finding in contract.findings if finding.priority == Priority.P1)
    assert all(finding.acceptance_criteria for finding in contract.findings if finding.priority == Priority.P1)
    assert all(finding.cost_of_inaction.mode == "qualitative" for finding in contract.findings)
    assert all(finding.cost_of_inaction.amount_base is None for finding in contract.findings)
    assert contract.readiness_status == ReadinessStatus.HUMAN_REVIEW_REQUIRED


def test_required_scanner_failure_prevents_client_ready_status() -> None:
    contract = build_decision_grade_contract(
        identity=_identity(),
        assessment=_assessment([_record(1, category="evidence")]),
        stage_summaries=[
            {
                "stage": "scanner_execution",
                "scanner_results": [
                    {
                        "tool": "semgrep",
                        "status": "failed",
                        "required": True,
                        "category": "static",
                        "reason": "worker process limit",
                    }
                ],
            }
        ],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=10,
        core_page_count=7,
    )

    assert contract.scanner_executions[0].status == EvidenceStatus.FAILED
    assert contract.readiness_status == ReadinessStatus.EVIDENCE_INCOMPLETE
    assert any(issue.code == "required_scanner_evidence_incomplete" for issue in contract.validation_issues)


def test_unsupported_benchmark_language_blocks_delivery() -> None:
    assessment = _assessment([_record(1)])
    assessment["executive_summary"] = "Complexity is in the top quartile for projects of this size."
    contract = build_decision_grade_contract(
        identity=_identity(),
        assessment=assessment,
        stage_summaries=[],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=10,
        core_page_count=7,
    )

    assert contract.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
    assert any(issue.code == "unsupported_benchmark_claim" for issue in contract.validation_issues)


def test_evidence_adjusted_score_cannot_exceed_technical_score() -> None:
    assessment = _assessment([_record(1)])
    assessment["technical_score"] = 70
    assessment["canonical_evidence_adjusted_score"] = 88
    contract = build_decision_grade_contract(
        identity=_identity(),
        assessment=assessment,
        stage_summaries=[],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=10,
        core_page_count=7,
    )

    assert contract.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
    assert any(issue.code == "evidence_adjusted_exceeds_technical" for issue in contract.validation_issues)
