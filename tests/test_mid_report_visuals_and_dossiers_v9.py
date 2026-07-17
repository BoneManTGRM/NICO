from nico.mid_report_visuals_and_dossiers_v9 import build_mid_finding_dossiers, build_mid_visual_data


def _fixture() -> dict:
    return {
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture",
                "score": 88,
                "evidence": ["Module graph retained.", "Dependency direction retained."],
                "findings": ["Compatibility surface requires review.", "Compatibility surface requires review."],
                "unavailable": [],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 62,
                "evidence": ["Semgrep artifact retained."],
                "findings": ["Bandit failed during exact-snapshot execution."],
                "unavailable": ["Bandit output unavailable."],
            },
        ],
        "mid_score_transparency": {
            "records": [
                {
                    "section_id": "architecture_debt",
                    "label": "Architecture",
                    "source_score": 88,
                    "presented_score": 74,
                    "status": "yellow",
                    "confidence": "review-limited",
                    "deductions": [{"reason": "Open finding", "points": 6}],
                },
                {
                    "section_id": "static_analysis",
                    "label": "Static Analysis",
                    "source_score": 62,
                    "presented_score": 44,
                    "status": "red",
                    "confidence": "review-limited",
                    "deductions": [{"reason": "Analyzer failed", "points": 10}],
                },
            ]
        },
        "repair_intelligence": {
            "candidates": [
                {
                    "title": "Compatibility surface requires review.",
                    "category": "architecture risk",
                    "severity": "high",
                    "confidence": "medium",
                    "business_impact": "Regression probability and maintenance cost increase.",
                    "technical_impact": "Import order can change runtime behavior.",
                    "root_cause": "Multiple compatibility installers mutate shared module state.",
                    "recommended_action": "Move installer registration behind one explicit bootstrap registry.",
                    "owner": "Platform engineering",
                    "effort": "3-5 engineer-days",
                    "dependencies": ["Import-order tests", "Bootstrap registry design"],
                    "verification": "Run import-order matrix, full suite, and production smoke tests.",
                    "rollback": "Restore prior bootstrap registry and redeploy the last verified image.",
                    "acceptance_criteria": "All supported import orders produce identical bindings.",
                    "deferred_risk": "Additional compatibility patches can create hidden recursion.",
                    "target_window": "Days 0-30",
                }
            ]
        },
    }


def test_mid_dossiers_are_complete_stable_and_deduplicated() -> None:
    result = _fixture()
    first = build_mid_finding_dossiers(result)
    second = build_mid_finding_dossiers(result)
    assert len(first) == 2
    assert [item.finding_id for item in first] == [item.finding_id for item in second]
    architecture = next(item for item in first if item.section_id == "architecture_debt")
    assert architecture.finding_id.startswith("MID-")
    assert architecture.business_impact != "Not provided"
    assert architecture.technical_impact != "Not provided"
    assert architecture.root_cause != "Not provided"
    assert architecture.repair != "Not provided"
    assert architecture.owner == "Platform engineering"
    assert architecture.dependencies
    assert architecture.verification != "Not provided"
    assert architecture.rollback != "Not provided"
    assert architecture.acceptance_criteria != "Not provided"
    assert architecture.deferred_risk != "Not provided"


def test_mid_visual_contract_contains_12_evidence_derived_views() -> None:
    result = _fixture()
    visuals = build_mid_visual_data(result)
    assert visuals["visual_count"] == 12
    for required in (
        "score_contribution",
        "status_distribution",
        "confidence_distribution",
        "severity_distribution",
        "finding_category_distribution",
        "evidence_funnel",
        "risk_heatmap",
        "repair_impact_matrix",
        "roadmap_windows",
        "ownership_assignments",
        "section_finding_density",
        "section_evidence_density",
    ):
        assert required in visuals
    assert visuals["evidence_funnel"]["dossiers"] == 2
    assert visuals["client_delivery_allowed"] is False
    assert visuals["human_review_required"] is True


def test_mid_visuals_preserve_score_deductions_and_distribution_truth() -> None:
    result = _fixture()
    visuals = build_mid_visual_data(result)
    architecture = next(item for item in visuals["score_contribution"] if item["section_id"] == "architecture_debt")
    assert architecture["source_score"] == 88
    assert architecture["presented_score"] == 74
    assert architecture["deduction_total"] == 6
    assert visuals["status_distribution"] == {"yellow": 1, "red": 1}
    assert visuals["confidence_distribution"] == {"review-limited": 2}
