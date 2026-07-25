from __future__ import annotations

from nico.decision_grade_acceptance_v1 import (
    apply_acceptance_criteria_engine,
    install_decision_grade_acceptance_engine,
    wrap_contract_builder,
)
from nico.decision_grade_contract_v1 import Priority, build_decision_grade_contract

COMMIT = "e" * 40
VALIDATION_COMMIT = "f" * 40


def _record(
    index: int,
    *,
    priority: str = "P1",
    category: str = "architecture",
    acceptance: str = "Improve the architecture",
) -> dict[str, object]:
    return {
        "id": f"legacy-{index}",
        "priority": priority,
        "category": category,
        "title": f"Decision-grade {category} risk {index}",
        "impact": "The unresolved condition can increase release delay, regressions, and engineering rework.",
        "confidence": "high",
        "evidence": f"measurement={40 + index}; category={category}",
        "location": f"src/module_{index}.py:{20 + index}",
        "recommendation": "Implement the bounded remediation and verify it on an immutable validation commit.",
        "effort": "2-4 weeks",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": acceptance,
    }


def _roadmap() -> list[dict[str, object]]:
    return [
        {
            "window": "0-30 days",
            "objective": "Close the highest-priority verified risks.",
            "work_packages": [
                {
                    "title": "Close decision-grade risks",
                    "objective": "Implement and verify the bounded remediations.",
                    "owner_role": "Product Engineering Architect",
                    "supporting_roles": [],
                    "effort": "2-4 weeks",
                    "dependencies": [],
                    "acceptance_criteria": ["Improve the implementation"],
                    "expected_impact": "Reduces release and regression exposure.",
                }
            ],
        }
    ]


def _assessment(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "technical_score": 80,
        "canonical_evidence_adjusted_score": 76,
        "findings_register": records,
        "sections": [],
        "scoring_weights": [],
    }


def _contract(records: list[dict[str, object]] | None = None):
    source = records or [_record(1)]
    assessment = _assessment(source)
    contract = build_decision_grade_contract(
        identity={
            "run_id": "comprun_acceptance_test",
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
        generated_at="2026-07-25T12:00:00+00:00",
    )
    return contract, assessment


def _kind(criterion) -> str:
    method = criterion.validation_method.casefold()
    if criterion.workflow_name or "workflow" in method:
        return "workflow"
    if criterion.test_name or "test" in method:
        return "test"
    return "implementation"


def test_p1_receives_implementation_test_and_workflow_criteria() -> None:
    contract, assessment = _contract()
    assessment["acceptance_validation_commit_sha"] = VALIDATION_COMMIT
    assessment["acceptance_workflow_name"] = "NICO CI"
    adjusted, summary = apply_acceptance_criteria_engine(contract, assessment)

    criteria = adjusted.findings[0].acceptance_criteria
    assert len(criteria) >= 3
    assert {"implementation", "test", "workflow"}.issubset({_kind(item) for item in criteria})
    assert all(item.target_commit_sha == VALIDATION_COMMIT for item in criteria)
    assert all(item.comparator is not None for item in criteria)
    assert all(item.target_value is not None for item in criteria)
    assert all(item.required_evidence for item in criteria)
    assert summary["p0_p1_implementation_test_workflow_coverage"] is True


def test_architecture_template_is_metric_bound_and_binary() -> None:
    contract, assessment = _contract()
    adjusted, _ = apply_acceptance_criteria_engine(contract, assessment)

    implementation = next(item for item in adjusted.findings[0].acceptance_criteria if _kind(item) == "implementation")
    assert implementation.metric == "cyclomatic_complexity"
    assert implementation.comparator == "<="
    assert implementation.target_value == 30
    assert implementation.file_path == "src/module_1.py"


def test_dependency_template_queries_locked_graph_for_absence() -> None:
    contract, assessment = _contract([_record(1, category="dependency")])
    adjusted, _ = apply_acceptance_criteria_engine(contract, assessment)

    implementation = next(item for item in adjusted.findings[0].acceptance_criteria if _kind(item) == "implementation")
    assert implementation.validation_method == "locked_graph_query"
    assert implementation.repository_query.startswith("locked_dependency_graph::")
    assert implementation.comparator == "absent"
    assert implementation.dependency_identifier


def test_ci_template_requires_zero_unresolved_blocking_failures() -> None:
    contract, assessment = _contract([_record(1, category="ci_cd")])
    assessment["acceptance_workflow_name"] = "Release Validation"
    adjusted, _ = apply_acceptance_criteria_engine(contract, assessment)

    implementation = next(item for item in adjusted.findings[0].acceptance_criteria if item.metric == "unresolved_blocking_failures")
    assert implementation.workflow_name == "Release Validation"
    assert implementation.comparator == "="
    assert implementation.target_value == 0


def test_vague_source_criterion_is_replaced_and_disclosed() -> None:
    contract, assessment = _contract()
    source_id = contract.findings[0].acceptance_criteria[0].criterion_id
    adjusted, summary = apply_acceptance_criteria_engine(contract, assessment)

    assert source_id not in {item.criterion_id for item in adjusted.findings[0].acceptance_criteria}
    assert any(item.code == "acceptance_criterion_replaced" for item in adjusted.validation_issues)
    assert summary["source_or_drafted_criteria_rejected"] >= 1


def test_valid_contextual_draft_is_retained_after_validation() -> None:
    contract, assessment = _contract()
    finding_id = contract.findings[0].finding_id
    assessment["drafted_acceptance_criteria"] = {
        finding_id: {
            "description": "The named module records zero unresolved architecture threshold violations.",
            "validation_method": "metric_comparison",
            "file_path": "src/module_1.py",
            "symbol_or_control": "module_1",
            "metric": "unresolved_architecture_threshold_violations",
            "comparator": "=",
            "target_value": 0,
            "required_evidence": ["Complexity scanner result", "Validation commit SHA"],
        }
    }
    adjusted, summary = apply_acceptance_criteria_engine(contract, assessment)

    retained = [item for item in adjusted.findings[0].acceptance_criteria if "zero unresolved architecture" in item.description]
    assert len(retained) == 1
    assert retained[0].metric == "unresolved_architecture_threshold_violations"
    assert summary["language_model_drafts_accepted_only_after_validation"] is True


def test_p2_receives_binary_implementation_without_forced_three_part_coverage() -> None:
    contract, assessment = _contract([_record(1, priority="P2", category="static")])
    adjusted, _ = apply_acceptance_criteria_engine(contract, assessment)

    finding = adjusted.findings[0]
    assert finding.priority == Priority.P2
    assert len(finding.acceptance_criteria) >= 1
    assert "implementation" in {_kind(item) for item in finding.acceptance_criteria}
    assert not {"implementation", "test", "workflow"}.issubset({_kind(item) for item in finding.acceptance_criteria})


def test_p1_roadmap_package_receives_binary_workflow_criterion() -> None:
    contract, assessment = _contract()
    assessment["acceptance_workflow_name"] = "NICO CI"
    adjusted, summary = apply_acceptance_criteria_engine(contract, assessment)

    package = adjusted.roadmap_work_packages[0]
    workflow = next(item for item in package.acceptance_criteria if _kind(item) == "workflow")
    assert workflow.workflow_name == "NICO CI"
    assert workflow.comparator == "="
    assert workflow.target_value == "success"
    assert summary["roadmap_criteria_generated"] >= 1


def test_wrapper_records_machine_readable_acceptance_summary() -> None:
    assessment = _assessment([_record(1)])
    wrapped = wrap_contract_builder(build_decision_grade_contract)
    contract = wrapped(
        identity={
            "run_id": "comprun_acceptance_wrapper",
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

    assert len(contract.findings[0].acceptance_criteria) >= 3
    assert assessment["decision_grade_acceptance"]["schema_version"] == "nico.decision_grade_acceptance.v1"


def test_installer_is_idempotent() -> None:
    class ReportModule:
        build_decision_grade_contract = staticmethod(build_decision_grade_contract)

    first = install_decision_grade_acceptance_engine(ReportModule)
    second = install_decision_grade_acceptance_engine(ReportModule)

    assert first["bound"] is True
    assert second["bound"] is True
    assert second["p0_p1_multi_criterion_coverage_required"] is True
