from nico.comprehensive_premium_synthesis_v6 import polish_assessment


def _assessment():
    return {
        "maturity_signal": {"score": 69, "presented_score": 69},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 82, "presented_score": 82, "score_value": 82, "assurance_label": "REVIEW LIMITED"},
            {"id": "dependency_health", "label": "Dependency", "score": 62, "presented_score": 62, "score_value": 62, "assurance_label": "BLOCKED"},
            {"id": "secrets_review", "label": "Secrets", "score": 85, "presented_score": 85, "score_value": 85, "assurance_label": "REVIEW LIMITED"},
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 21,
                "presented_score": 21,
                "score_value": 21,
                "assurance_label": "BLOCKED",
                "evidence": ["Static candidates: raw=108; material=39; review_required=69.", "Failed static tools: bandit."],
                "findings": ["Failed static analyzers: bandit.", "69 static-analysis candidate(s) require human triage."],
                "unavailable": ["Bandit output incomplete."],
            },
            {"id": "ci_cd", "label": "CI/CD", "score": 74, "presented_score": 74, "score_value": 74, "assurance_label": "REVIEW LIMITED"},
            {"id": "architecture_debt", "label": "Architecture", "score": 78, "presented_score": 78, "score_value": 78, "assurance_label": "REVIEW LIMITED"},
            {"id": "velocity_complexity", "label": "Velocity", "score": 84, "presented_score": 84, "score_value": 84, "assurance_label": "VERIFIED"},
        ],
        "findings_register": [
            {
                "id": "architecture-hotspot-1",
                "priority": "P1",
                "category": "architecture",
                "title": "Complexity hotspot: <module-logic>",
                "location": "apps/web/app/assessment/MidSectionReview.tsx:1",
                "impact": "impact",
                "confidence": "moderate",
                "evidence": "cyclomatic_complexity=148",
                "recommendation": "recommend",
                "acceptance_criteria": "accept",
                "owner_role": "Architect",
                "effort": "M-L",
            },
            {
                "id": "static-1",
                "priority": "P1",
                "category": "static",
                "title": "mutable action tag",
                "location": ".github/workflows/codeql.yml",
                "impact": "impact",
                "confidence": "moderate",
                "evidence": "severity=medium; verified=False",
                "recommendation": "recommend",
                "acceptance_criteria": "accept",
                "owner_role": "Engineer",
                "effort": "S-M",
            },
        ],
    }


def test_incomplete_static_is_not_scored_or_counted_as_zero():
    result = polish_assessment(_assessment())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    assert static["score_value"] is None
    assert static["technical_score_display"] == "NOT SCORED"
    assert static["assurance_label"] == "BLOCKED"
    assert "static_analysis" in result["maturity_signal"]["unscored_controls_excluded"]
    assert result["maturity_signal"]["presented_score"] > 69


def test_unverified_medium_candidate_is_not_p1_and_module_name_is_client_facing():
    result = polish_assessment(_assessment())
    static = next(item for item in result["findings_register"] if item["category"] == "static")
    architecture = next(item for item in result["findings_register"] if item["category"] == "architecture")
    assert static["priority"] == "P2"
    assert "<module-logic>" not in architecture["title"]
    assert "MidSectionReview" in architecture["title"]


def test_executive_register_is_consolidated_and_weighting_is_explicit():
    result = polish_assessment(_assessment())
    assert 1 <= len(result["executive_risk_register"]) <= 8
    assert result["scoring_weights"]
    assert all("weight_percent" in item for item in result["scoring_weights"])
    assert result["premium_synthesis"]["executive_risks_consolidated"] is True
