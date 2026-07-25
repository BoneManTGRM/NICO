from __future__ import annotations

from nico.decision_grade_contract_v1 import ReadinessStatus, build_decision_grade_contract
from nico.decision_grade_cost_engine_v1 import (
    CostOfInactionInputs,
    apply_cost_of_inaction_inputs,
    install_decision_grade_cost_engine,
    wrap_contract_builder,
)

COMMIT = "d" * 40


def _identity() -> dict[str, object]:
    return {
        "run_id": "comprun_cost_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "assessment_type": "comprehensive",
        "branch": "main",
        "nico_version": "0.1.1",
        "scanner_configuration_version": "test-v1",
    }


def _record(index: int, *, category: str = "architecture") -> dict[str, object]:
    return {
        "id": f"legacy-{index}",
        "priority": "P1",
        "category": category,
        "title": f"Decision-grade risk {index}",
        "impact": "The unresolved condition can create engineering rework and release delay.",
        "confidence": "high",
        "evidence": f"measurement={40 + index}",
        "location": f"src/module_{index}.py:{20 + index}",
        "recommendation": "Implement the bounded remediation and verify it against the validation commit.",
        "effort": "2-4 weeks",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": f"module_{index} metric <= 30 and its validation workflow passes.",
    }


def _roadmap() -> list[dict[str, object]]:
    return [
        {
            "window": "0-30 days",
            "objective": "Close the highest-priority risks.",
            "work_packages": [
                {
                    "title": "Close decision-grade risks",
                    "objective": "Implement and verify the bounded remediation.",
                    "owner_role": "Product Engineering Architect",
                    "effort": "2-4 weeks",
                    "dependencies": [],
                    "acceptance_criteria": ["The validation workflow passes on the remediation commit"],
                    "expected_impact": "Reduces release and rework exposure.",
                }
            ],
        }
    ]


def _contract(record_count: int = 1):
    return build_decision_grade_contract(
        identity=_identity(),
        assessment={
            "technical_score": 82,
            "canonical_evidence_adjusted_score": 78,
            "findings_register": [_record(index) for index in range(1, record_count + 1)],
            "sections": [],
            "scoring_weights": [],
        },
        stage_summaries=[],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )


def test_scenario_mode_produces_transparent_hours_without_inventing_dollars() -> None:
    adjusted, summary = apply_cost_of_inaction_inputs(
        _contract(),
        {
            "mode": "scenario",
            "scenario_profile": "balanced",
            "source": "NICO planning scenario",
            "assumptions": ["No client labor rate was supplied."],
        },
    )

    cost = adjusted.findings[0].cost_of_inaction
    assert cost.mode == "scenario"
    assert cost.engineering_hours_low == 40
    assert cost.engineering_hours_high == 120
    assert cost.amount_low is None
    assert cost.amount_base is None
    assert cost.amount_high is None
    assert cost.currency is None
    assert "Formula:" in cost.rationale
    assert summary["monetary_conversion_performed"] is False
    assert summary["unsupported_dollar_amount_generated"] is False


def test_scenario_mode_converts_hours_only_when_rate_and_currency_are_supplied() -> None:
    adjusted, summary = apply_cost_of_inaction_inputs(
        _contract(),
        {
            "mode": "scenario",
            "scenario_profile": "balanced",
            "source": "Client planning workshop",
            "currency": "USD",
            "blended_engineering_cost_per_hour": 100,
            "assumptions": ["The supplied blended rate is valid for the 90-day planning period."],
        },
    )

    cost = adjusted.findings[0].cost_of_inaction
    assert cost.amount_low == 4000
    assert cost.amount_base == 8000
    assert cost.amount_high == 12000
    assert cost.currency == "USD"
    assert summary["monetary_conversion_performed"] is True


def test_client_input_mode_uses_exact_ranges_and_disclosed_formula() -> None:
    contract = _contract()
    finding_id = contract.findings[0].finding_id
    adjusted, summary = apply_cost_of_inaction_inputs(
        contract,
        {
            "mode": "client_input",
            "source": "Client financial intake 2026-07-25",
            "currency": "USD",
            "timeframe_days": 90,
            "blended_engineering_cost_per_hour": 100,
            "release_delay_cost_per_day": 500,
            "assumptions": [
                "Engineering hours and release-delay values were supplied by the client.",
                "The blended engineering rate excludes taxes and procurement overhead.",
            ],
            "finding_estimates": {
                finding_id: {
                    "engineering_hours_low": 10,
                    "engineering_hours_base": 20,
                    "engineering_hours_high": 30,
                    "direct_cost_low": 100,
                    "direct_cost_base": 200,
                    "direct_cost_high": 300,
                    "release_delay_days_low": 1,
                    "release_delay_days_base": 2,
                    "release_delay_days_high": 3,
                    "confidence": "high",
                }
            },
        },
    )

    cost = adjusted.findings[0].cost_of_inaction
    assert cost.mode == "client_input"
    assert cost.amount_low == 1600
    assert cost.amount_base == 3200
    assert cost.amount_high == 4800
    assert cost.currency == "USD"
    assert cost.timeframe_days == 90
    assert "engineering hours low/base/high=10/20/30" in cost.rationale
    assert "direct cost low/base/high=100/200/300" in cost.rationale
    assert "release-delay days low/base/high=1/2/3" in cost.rationale
    assert adjusted.assumptions[0].user_supplied is True
    assert adjusted.assumptions[0].source == "Client financial intake 2026-07-25"
    assert summary["quantified_finding_ids"] == [finding_id]


def test_client_input_mode_keeps_unmapped_findings_qualitative() -> None:
    contract = _contract(record_count=2)
    first_id = contract.findings[0].finding_id
    adjusted, summary = apply_cost_of_inaction_inputs(
        contract,
        {
            "mode": "client_input",
            "source": "Client intake",
            "currency": "USD",
            "blended_engineering_cost_per_hour": 100,
            "assumptions": ["Only the first finding was estimated by the client."],
            "finding_estimates": {
                first_id: {
                    "engineering_hours_low": 10,
                    "engineering_hours_base": 20,
                    "engineering_hours_high": 30,
                }
            },
        },
    )

    assert adjusted.findings[0].cost_of_inaction.mode == "client_input"
    assert adjusted.findings[1].cost_of_inaction.mode == "qualitative"
    assert summary["quantified_finding_count"] == 1
    assert summary["unquantified_finding_count"] == 1
    assert any(item.assumption_id == "ASM-FIN-GAP-001" for item in adjusted.assumptions)


def test_invalid_client_input_blocks_delivery_without_using_the_values() -> None:
    adjusted, summary = apply_cost_of_inaction_inputs(
        _contract(),
        {
            "mode": "client_input",
            "source": "Client intake",
            "currency": "USD",
            "blended_engineering_cost_per_hour": 100,
            "assumptions": [],
            "default_estimate": {
                "engineering_hours_low": 10,
                "engineering_hours_base": 20,
                "engineering_hours_high": 30,
            },
        },
    )

    assert adjusted.readiness_status == ReadinessStatus.DELIVERY_BLOCKED
    assert adjusted.findings[0].cost_of_inaction.mode == "qualitative"
    assert any(item.code == "cost_of_inaction_inputs_invalid" for item in adjusted.validation_issues)
    assert summary["status"] == "invalid"


def test_wrapper_reads_inputs_from_assessment_and_records_engine_summary() -> None:
    assessment = {
        "technical_score": 82,
        "canonical_evidence_adjusted_score": 78,
        "findings_register": [_record(1)],
        "sections": [],
        "scoring_weights": [],
        "cost_of_inaction_inputs": {
            "mode": "scenario",
            "source": "NICO planning scenario",
            "assumptions": ["Scenario values are not client actuals."],
        },
    }
    wrapped = wrap_contract_builder(build_decision_grade_contract)
    contract = wrapped(
        identity=_identity(),
        assessment=assessment,
        stage_summaries=[],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
    )

    assert contract.findings[0].cost_of_inaction.mode == "scenario"
    assert assessment["cost_of_inaction_engine"]["status"] == "complete"


def test_installer_binds_contract_builder_idempotently() -> None:
    class ReportModule:
        build_decision_grade_contract = staticmethod(build_decision_grade_contract)

    first = install_decision_grade_cost_engine(ReportModule)
    second = install_decision_grade_cost_engine(ReportModule)

    assert first["bound"] is True
    assert second["bound"] is True
    assert CostOfInactionInputs.model_validate({"mode": "qualitative"}).mode == "qualitative"
