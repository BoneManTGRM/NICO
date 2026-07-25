from __future__ import annotations

import io

from pypdf import PdfReader

from nico.comprehensive_decision_grade_html_v5 import _build_html
from nico.comprehensive_decision_grade_markdown_v5 import _build_markdown
from nico.comprehensive_premium_pdf_v6 import _pdf_with_final_count
from nico.decision_grade_contract_v1 import build_decision_grade_contract
from nico.decision_grade_report_view_v1 import apply_report_view, build_report_view


COMMIT = "c" * 40


def _record(index: int, *, priority: str = "P1", category: str = "architecture") -> dict[str, object]:
    return {
        "id": f"legacy-{index}",
        "priority": priority,
        "category": category,
        "title": f"Decision-grade risk {index}",
        "impact": f"Risk {index} can delay releases and increase engineering rework.",
        "confidence": "high",
        "evidence": f"cyclomatic_complexity={40 + index}; retained=true",
        "location": f"src/module_{index}.py:{20 + index}",
        "recommendation": f"Decompose module {index} and enforce its validation workflow.",
        "effort": "2-4 weeks",
        "owner_role": "Product Engineering Architect",
        "acceptance_criteria": f"module_{index} cyclomatic complexity <= 30 and its validation workflow passes.",
    }


def _roadmap() -> list[dict[str, object]]:
    return [
        {
            "window": "0-30 days",
            "objective": "Close the highest-priority verified risks.",
            "work_packages": [
                {
                    "title": "Decompose architecture hotspots",
                    "objective": "Reduce concentrated complexity while preserving behavior.",
                    "owner_role": "Product Engineering Architect",
                    "effort": "2-4 weeks",
                    "dependencies": ["Characterization tests"],
                    "acceptance_criteria": ["Target cyclomatic complexity <= 30", "Validation workflow passes"],
                    "expected_impact": "Reduces regression and review cost.",
                }
            ],
        },
        {
            "window": "31-90 days",
            "objective": "Stabilize the improved architecture.",
            "work_packages": [
                {
                    "title": "Add preventive architecture controls",
                    "objective": "Prevent recurrence of concentrated complexity.",
                    "owner_role": "Product Engineering Architect",
                    "effort": "4-8 weeks",
                    "dependencies": ["Priority decomposition complete"],
                    "acceptance_criteria": ["Architecture controls execute in CI"],
                    "expected_impact": "Improves long-term maintainability.",
                }
            ],
        },
    ]


def _contract():
    return build_decision_grade_contract(
        identity={
            "run_id": "comprun_surface_test",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "assessment_type": "comprehensive",
            "branch": "main",
            "nico_version": "0.1.1",
            "scanner_configuration_version": "test-v1",
        },
        assessment={
            "technical_score": 82,
            "canonical_evidence_adjusted_score": 76,
            "findings_register": [_record(index) for index in range(1, 9)],
            "sections": [],
            "scoring_weights": [],
        },
        stage_summaries=[
            {
                "stage": "scanner_execution",
                "scanner_results": [
                    {"tool": "semgrep", "status": "complete", "required": True, "category": "static"},
                    {"tool": "dependency_audit", "status": "partial", "required": True, "category": "dependency", "reason": "registry evidence limited"},
                ],
            }
        ],
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )


def _assessment() -> dict[str, object]:
    return {
        "technical_score": 82,
        "canonical_evidence_adjusted_score": 76,
        "evidence_adjusted_score": 76,
        "maturity_signal": {
            "score": 82,
            "presented_score": 82,
            "score_band_label": "STRONG",
            "evidence_readiness_score": 76,
        },
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture and debt",
                "score_value": 78,
                "score_band_label": "MODERATE",
                "score_tone": "yellow",
                "assurance_label": "REVIEW LIMITED",
                "technical_score_display": "MODERATE · 78/100",
                "summary": "Architecture evidence contains named hotspots.",
                "evidence": ["8 named modules measured"],
                "findings": ["module_8.py has the highest retained complexity"],
            }
        ],
        "scoring_weights": [
            {
                "control": "Architecture and debt",
                "weight_percent": 100,
                "technical_score": 78,
                "weighted_contribution": 78,
                "assurance": "REVIEW LIMITED",
                "included": True,
            }
        ],
        "findings_register": [_record(index) for index in range(1, 9)],
        "limitation_metrics": {"material_findings": 8},
        "comprehensive_express_quality": {"shared_control_truth_reconciled": True},
        "comprehensive_executive_risk_truth": {"static_risk_wording_reconciled": True},
    }


def _identity() -> dict[str, str]:
    return {
        "run_id": "comprun_surface_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "evidence_ledger_id": "ledger_surface_test",
        "customer_id": "customer_surface_test",
        "project_id": "project_surface_test",
    }


def _scanner_limitation_contract(*, with_structured_semgrep: bool = False):
    stage_summaries: list[dict[str, object]] = []
    if with_structured_semgrep:
        stage_summaries = [
            {
                "stage": "scanner_execution",
                "scanner_results": [
                    {"tool": "semgrep", "status": "complete", "required": True, "category": "static"},
                ],
            }
        ]
    findings = [
        {
            "id": "bandit-unavailable",
            "priority": "P1",
            "category": "evidence",
            "title": "bandit evidence unavailable",
            "impact": "The affected control cannot reach verified assurance because the required analyzer did not complete.",
            "confidence": "high",
            "evidence": "Analyzer status=failed; bounded output could not be verified.",
            "location": "Scanner execution boundary",
            "recommendation": "Repair Bandit execution and rerun two exact-SHA evidence passes.",
            "effort": "1-2 weeks",
            "owner_role": "Product Quality Engineer",
            "acceptance_criteria": "Bandit completes twice on one exact SHA.",
        },
        {
            "id": "osv-incomplete",
            "priority": "P2",
            "category": "dependency",
            "title": "OSV dependency scan did not produce a complete result",
            "impact": "Dependency vulnerability conclusions remain review-limited.",
            "confidence": "moderate",
            "evidence": "tool=osv-scanner; status=incomplete",
            "location": "Dependency scanner execution boundary",
            "recommendation": "Repair OSV execution and retain structured exact-SHA output.",
            "effort": "1 week",
            "owner_role": "Senior Product Engineer",
            "acceptance_criteria": "OSV completes with structured output.",
        },
    ]
    return build_decision_grade_contract(
        identity={
            "run_id": "comprun_scanner_limitation_test",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "assessment_type": "comprehensive",
            "branch": "main",
            "nico_version": "0.1.1",
            "scanner_configuration_version": "test-v1",
        },
        assessment={
            "technical_score": 82,
            "canonical_evidence_adjusted_score": 71,
            "findings_register": findings,
            "sections": [],
            "scoring_weights": [],
        },
        stage_summaries=stage_summaries,
        roadmap=_roadmap(),
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=12,
        core_page_count=8,
        generated_at="2026-07-25T12:00:00+00:00",
    )


def test_report_view_projects_stable_ids_cost_residual_scope_and_assumptions() -> None:
    view = build_report_view(_contract())

    assert len(view["executive_risk_register"]) == 7
    assert all(item["finding_id"].startswith("RISK-P1-") for item in view["executive_risk_register"])
    assert all(item["cost_of_inaction"] for item in view["executive_risk_register"])
    assert all(item["residual_risk"] for item in view["executive_risk_register"])
    assert view["evidence_health"]["required_scanner_failures"] == ["dependency_audit"]
    assert view["scope_boundaries"]
    assert view["assumption_register"]
    assert len(view["how_to_use"]) == 7


def test_evidence_health_uses_retained_findings_when_execution_records_are_missing() -> None:
    view = build_report_view(_scanner_limitation_contract())
    health = view["evidence_health"]

    assert health["structured_execution_records_present"] is False
    assert health["completed_scanners"] == []
    assert health["required_scanner_failures"] == ["bandit"]
    assert {item["scanner"] for item in health["finding_derived_scanner_limitations"]} == {
        "bandit",
        "osv-scanner",
    }
    assert "No scanner failure" not in health["confidence_effect"]
    assert "Required scanner limitations are retained" in health["confidence_effect"]


def test_evidence_health_combines_structured_completion_with_finding_limitations() -> None:
    view = build_report_view(_scanner_limitation_contract(with_structured_semgrep=True))
    health = view["evidence_health"]

    assert health["structured_execution_records_present"] is True
    assert health["completed_scanners"] == ["semgrep"]
    assert health["required_scanner_failures"] == ["bandit"]
    assert any(
        item["scanner"] == "bandit" and item["source"] == "retained_finding"
        for item in health["incomplete_scanners"]
    )


def test_markdown_and_html_use_exact_seven_item_executive_register() -> None:
    assessment = apply_report_view(_assessment(), _contract())
    roadmap = assessment["decision_grade_roadmap"]
    limitations = {
        "stages_with_limitations": 1,
        "individual_limitation_records": 1,
        "stage_limitation_records": 1,
        "assessment_wide_records": 0,
        "score_affecting_records": 1,
        "informational_records": 0,
    }
    markdown = _build_markdown(_identity(), assessment, [], roadmap, [], limitations, "2026-07-25T12:00:00+00:00")
    rendered_html = _build_html(_identity(), assessment, [], roadmap, [], limitations, "2026-07-25T12:00:00+00:00")

    executive_ids = [item["finding_id"] for item in assessment["executive_risk_register"]]
    overflow_id = next(
        item["finding_id"]
        for item in assessment["decision_grade_findings_register"]
        if item["finding_id"] not in set(executive_ids)
    )
    for finding_id in executive_ids:
        assert finding_id in markdown
        assert finding_id in rendered_html
    executive_markdown = markdown.split("## Executive Risk Register", 1)[1].split("## Detailed Findings Register", 1)[0]
    executive_html = rendered_html.split("<h2>Executive Risk Register</h2>", 1)[1].split("<h2>Detailed Findings Register</h2>", 1)[0]
    assert overflow_id not in executive_markdown
    assert overflow_id not in executive_html
    assert "Cost of inaction" in markdown
    assert "Residual risk" in markdown
    assert "Scope Boundary and Unassessed Risk" in markdown
    assert "Assumption Register" in rendered_html
    assert "Layer 1 — Evidence / fact" in rendered_html


def test_pdf_renders_decision_grade_sections_and_one_page_executive_brief() -> None:
    assessment = apply_report_view(_assessment(), _contract())
    roadmap = assessment["decision_grade_roadmap"]
    limitations = {
        "stages_with_limitations": 1,
        "individual_limitation_records": 1,
        "stage_limitation_records": 1,
        "assessment_wide_records": 0,
        "score_affecting_records": 1,
        "informational_records": 0,
    }
    pdf_bytes, page_count = _pdf_with_final_count(
        _identity(),
        assessment,
        [],
        roadmap,
        [],
        limitations,
        "2026-07-25T12:00:00+00:00",
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text = [page.extract_text() or "" for page in reader.pages]

    assert pdf_bytes.startswith(b"%PDF")
    assert page_count == len(reader.pages)
    assert "Executive Decision Brief" in page_text[1]
    assert "Technical Scorecard and Weighting" not in page_text[1]
    assert any("Executive Risk Register" in text for text in page_text)
    assert any("Cost of inaction" in text for text in page_text)
    assert any("Scope Boundary and Unassessed Risk" in text for text in page_text)
    assert any("Assumption Register" in text for text in page_text)
    assert any("Layer 1" in text and "Evidence / fact" in text for text in page_text)
