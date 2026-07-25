from __future__ import annotations

from nico.decision_grade_contract_v1 import ReadinessStatus, build_decision_grade_contract
from nico.decision_grade_human_evidence_binding_v1 import wrap_report_builder_with_human_evidence
from nico.decision_grade_human_evidence_v1 import (
    MODULE_DEFINITIONS,
    apply_human_evidence_to_contract,
    build_human_evidence_ledger,
    human_evidence_exports,
    human_evidence_intake_template,
)

COMMIT = "a" * 40


def _identity() -> dict[str, object]:
    return {
        "run_id": "comprun_human_evidence",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "evidence_ledger_id": "ledger_human",
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


def _complete_functional_qa() -> dict[str, object]:
    return {
        "test_cases": [
            {
                "test_id": "QA-1",
                "scenario": "Create assessment",
                "environment": "production",
                "expected": "Run starts",
                "actual": "Run starts",
                "status": "pass",
                "severity": "none",
                "evidence_reference": "video://qa-1",
            }
        ],
        "observed_results": [{"test_id": "QA-1", "status": "pass"}],
        "reviewer": "QA Reviewer",
        "observed_at": "2026-07-25T12:00:00Z",
        "source_reference": "qa-session-1",
    }


def test_missing_human_modules_are_explicitly_not_assessed() -> None:
    ledger = build_human_evidence_ledger(identity=_identity(), stage_results={})

    assert ledger["module_count"] == len(MODULE_DEFINITIONS) == 10
    assert ledger["status"] == "review_limited"
    assert len(ledger["incomplete_modules"]) == 10
    assert all(item["status"] == "not_assessed" for item in ledger["modules"])
    assert ledger["repository_inference_allowed"] is False


def test_complete_module_requires_named_reviewer_time_and_source() -> None:
    ledger = build_human_evidence_ledger(
        identity={**_identity(), "human_evidence_inputs": {"functional_qa": _complete_functional_qa()}},
        stage_results={},
    )
    module = next(item for item in ledger["modules"] if item["module_id"] == "functional_qa")

    assert module["status"] == "complete"
    assert module["reviewer"] == "QA Reviewer"
    assert module["missing_fields"] == []
    assert module["missing_metadata"] == []


def test_explicit_exclusion_requires_rationale() -> None:
    invalid = build_human_evidence_ledger(
        identity={"human_evidence_inputs": {"functional_qa": {"excluded": True}}},
        stage_results={},
    )
    valid = build_human_evidence_ledger(
        identity={
            "human_evidence_inputs": {
                "functional_qa": {
                    "excluded": True,
                    "exclusion_rationale": "The assessed service has no interactive user surface.",
                }
            }
        },
        stage_results={},
    )

    invalid_module = next(item for item in invalid["modules"] if item["module_id"] == "functional_qa")
    valid_module = next(item for item in valid["modules"] if item["module_id"] == "functional_qa")
    assert invalid_module["status"] == "partial"
    assert "exclusion_rationale" in invalid_module["missing_metadata"]
    assert valid_module["status"] == "excluded"


def test_incomplete_human_evidence_constrains_contract_readiness() -> None:
    ledger = build_human_evidence_ledger(identity=_identity(), stage_results={})
    adjusted = apply_human_evidence_to_contract(_contract(), ledger)

    assert adjusted.readiness_status == ReadinessStatus.EVIDENCE_INCOMPLETE
    assert any(item.code == "human_evidence_incomplete" for item in adjusted.validation_issues)


def test_exports_include_intake_qa_parity_decision_and_hashes() -> None:
    ledger = build_human_evidence_ledger(
        identity={**_identity(), "human_evidence_inputs": {"functional_qa": _complete_functional_qa()}},
        stage_results={},
    )
    exports = human_evidence_exports(ledger)

    assert exports["ledger_json"].startswith("{")
    assert "test_id,scenario,environment" in exports["qa_register_csv"]
    assert "surface,platform,operating_system" in exports["parity_matrix_csv"]
    assert "module_id,decision_id,decision" in exports["stakeholder_decision_log_csv"]
    assert len(exports["hashes"]) == 5
    assert exports["client_delivery_allowed"] is False


def test_intake_template_covers_every_required_module() -> None:
    template = human_evidence_intake_template()

    assert len(template["modules"]) == 10
    assert {item["module_id"] for item in template["modules"]} == {
        item["module_id"] for item in MODULE_DEFINITIONS
    }
    assert all("reviewer" in item and "observed_at" in item and "source_reference" in item for item in template["modules"])


def test_report_wrapper_attaches_machine_readable_and_rendered_surfaces() -> None:
    contract = _contract().model_dump(mode="json")

    def delegate(*, identity, stage_results):
        return {
            "assessment": _assessment(),
            "decision_grade_contract": contract,
            "report_package": {
                "decision_grade_contract": contract,
                "markdown": "# Report\n",
                "html": "<html><body><h1>Report</h1></body></html>",
                "json": {},
                "quality": {},
            },
        }

    wrapped = wrap_report_builder_with_human_evidence(delegate)
    result = wrapped(
        identity={**_identity(), "current_stage": "final_comprehensive_report_generation"},
        stage_results={"final_comprehensive_report_generation": {"status": "running"}},
    )
    package = result["report_package"]

    assert result["strategic_human_evidence"]["module_count"] == 10
    assert "## Strategic Human Evidence" in package["markdown"]
    assert '<section id="strategic-human-evidence">' in package["html"]
    assert package["json"]["strategic_human_evidence"]["module_count"] == 10
    assert package["quality"]["human_evidence_repository_inference_allowed"] is False
    assert package["client_delivery_allowed"] is False
