from nico.comprehensive_executive_risk_truth_v7 import reconcile_executive_risk_truth


def test_scored_static_control_uses_assurance_language_in_executive_risk():
    assessment = {
        "sections": [
            {
                "id": "static_analysis",
                "score_value": 82,
                "exclude_from_maturity": False,
                "assurance_label": "REVIEW LIMITED",
            }
        ],
        "executive_risk_register": [
            {
                "priority": "P1",
                "title": "Static-analysis evidence incomplete",
                "impact": "Incomplete analyzer execution prevents a defensible technical conclusion for the affected control.",
                "recommendation": "Repair the analyzer before assigning a technical score.",
            }
        ],
    }

    result = reconcile_executive_risk_truth(assessment)
    risk = result["executive_risk_register"][0]

    assert risk["title"] == "Static-analysis assurance remains review-limited"
    assert "conservative technical signal" in risk["impact"]
    assert "verified assurance" in risk["recommendation"]
    assert result["comprehensive_executive_risk_truth"]["static_risk_wording_reconciled"] is True
