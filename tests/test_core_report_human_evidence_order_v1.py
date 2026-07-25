from __future__ import annotations

from nico.decision_grade_contract_v1 import ReadinessStatus, build_decision_grade_contract
from nico.decision_grade_human_evidence_binding_v1 import wrap_report_builder_with_human_evidence

COMMIT = "a" * 40


def _identity() -> dict[str, object]:
    return {
        "run_id": "comprun_order_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "customer_id": "customer_test",
        "project_id": "project_test",
        "assessment_type": "comprehensive",
        "branch": "main",
        "nico_version": "0.1.1",
        "scanner_configuration_version": "test-v1",
    }


def _assessment() -> dict[str, object]:
    return {
        "technical_score": 80,
        "canonical_evidence_adjusted_score": 76,
        "findings_register": [
            {
                "id": "legacy-1",
                "priority": "P1",
                "category": "architecture",
                "title": "Architecture hotspot",
                "impact": "The condition can delay releases.",
                "confidence": "high",
                "evidence": "cyclomatic_complexity=42",
                "location": "src/module.py:20",
                "recommendation": "Decompose the module.",
                "effort": "2-4 weeks",
                "owner_role": "Product Engineering Architect",
                "acceptance_criteria": "src/module.py cyclomatic complexity <= 30.",
            }
        ],
        "sections": [],
        "scoring_weights": [],
    }


def _contract():
    return build_decision_grade_contract(
        identity=_identity(),
        assessment=_assessment(),
        stage_summaries=[],
        roadmap=[
            {
                "window": "0-30 days",
                "objective": "Close architecture risk.",
                "work_packages": [
                    {
                        "title": "Decompose module",
                        "objective": "Reduce complexity.",
                        "owner_role": "Product Engineering Architect",
                        "effort": "2-4 weeks",
                        "dependencies": [],
                        "acceptance_criteria": ["src/module.py cyclomatic complexity <= 30."],
                        "expected_impact": "Reduced regression exposure.",
                    }
                ],
            }
        ],
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )


def _delegate(*, identity, stage_results):
    contract = _contract().model_dump(mode="json")
    return {
        "assessment": _assessment(),
        "decision_grade_contract": contract,
        "delivery_status": ReadinessStatus.HUMAN_REVIEW_REQUIRED.value,
        "report_package": {
            "decision_grade_contract": contract,
            "delivery_status": ReadinessStatus.HUMAN_REVIEW_REQUIRED.value,
            "markdown": "# Core Decision Report\n",
            "html": "<html><body><h1>Core Decision Report</h1></body></html>",
            "json": {},
            "quality": {},
        },
    }


def test_core_report_does_not_fail_before_strategic_human_evidence_stages_run() -> None:
    wrapped = wrap_report_builder_with_human_evidence(_delegate)
    result = wrapped(
        identity={**_identity(), "current_stage": "decision_report_generation"},
        stage_results={
            "evidence_reconciliation_and_scoring": {"status": "complete", "technical_score": 80},
        },
    )

    package = result["report_package"]
    contract = package["decision_grade_contract"]
    issue_codes = {item["code"] for item in contract["validation_issues"]}

    assert result["human_evidence_gate_deferred"] is True
    assert package["human_evidence_gate_deferred"] is True
    assert package["quality"]["human_evidence_gate_applied"] is False
    assert "human_evidence_incomplete" not in issue_codes
    assert package["delivery_status"] == ReadinessStatus.HUMAN_REVIEW_REQUIRED.value
    assert "## Strategic Human Evidence" not in package["markdown"]


def test_final_report_applies_human_evidence_gate_after_strategic_collection_starts() -> None:
    wrapped = wrap_report_builder_with_human_evidence(_delegate)
    result = wrapped(
        identity={**_identity(), "current_stage": "final_comprehensive_report_generation"},
        stage_results={
            "functional_qa": {"status": "complete", "message": "QA stage completed without retained human observations."},
            "final_comprehensive_report_generation": {"status": "running"},
        },
    )

    package = result["report_package"]
    contract = package["decision_grade_contract"]
    issue_codes = {item["code"] for item in contract["validation_issues"]}

    assert result["human_evidence_gate_deferred"] is False
    assert package["quality"]["human_evidence_gate_applied"] is True
    assert "human_evidence_incomplete" in issue_codes
    assert package["delivery_status"] == ReadinessStatus.EVIDENCE_INCOMPLETE.value
    assert "## Strategic Human Evidence" in package["markdown"]
