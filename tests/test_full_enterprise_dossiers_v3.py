from nico.full_enterprise_dossiers_v3 import build_enterprise_dossiers, build_enterprise_visual_data


def _fixture() -> dict:
    return {
        "sections": [
            {
                "id": "architecture",
                "evidence": ["Exact service inventory", "Dependency graph artifact"],
                "findings": ["Service ownership is concentrated.", "Service ownership is concentrated."],
            },
            {
                "id": "release",
                "evidence": ["Release workflow evidence"],
                "findings": ["Release rollback evidence requires review."],
            },
        ],
        "repair_intelligence": {
            "candidates": [
                {
                    "title": "Service ownership is concentrated.",
                    "classification": "organizational dependency",
                    "severity": "high",
                    "priority": "P1",
                    "confidence": "high",
                    "business_impact": "Delivery continuity depends on too few maintainers.",
                    "technical_impact": "Critical service knowledge and change authority are concentrated.",
                    "root_cause": "Ownership distribution has not kept pace with system growth.",
                    "recommended_action": "Assign secondary owners and prove handoff readiness.",
                    "owner": "Engineering leadership",
                    "effort": "2-4 engineer-days",
                    "verification": "Validate CODEOWNERS, runbook handoff, and independent release exercise.",
                    "rollback": "Restore prior ownership rules if the new routing blocks urgent changes.",
                    "acceptance_criteria": "Two qualified owners can independently execute the release runbook.",
                    "deferred_risk": "Bus-factor and release continuity risk remain elevated.",
                    "target_window": "quarter 1",
                }
            ]
        },
    }


def test_enterprise_dossiers_are_complete_stable_and_deduplicated() -> None:
    first = build_enterprise_dossiers(_fixture())
    second = build_enterprise_dossiers(_fixture())
    assert len(first) == 2
    assert [item["finding_id"] for item in first] == [item["finding_id"] for item in second]
    required = {
        "finding_id", "section_id", "title", "classification", "severity", "priority",
        "confidence", "business_impact", "technical_impact", "evidence", "root_cause",
        "repair", "owner", "effort", "verification", "rollback", "acceptance_criteria",
        "deferred_risk", "target_window", "approval_required",
    }
    assert required <= set(first[0])
    assert first[0]["approval_required"] is True


def test_full_visual_model_has_enterprise_decision_views() -> None:
    result = _fixture()
    visuals = build_enterprise_visual_data(result)
    assert visuals["visual_count"] == 22
    for key in (
        "severity_distribution",
        "confidence_distribution",
        "classification_distribution",
        "ownership_distribution",
        "roadmap_distribution",
        "finding_density_by_section",
        "risk_heatmap",
        "repair_impact_matrix",
        "evidence_funnel",
    ):
        assert key in visuals
    assert result["full_enterprise_dossiers"]["human_review_required"] is True
