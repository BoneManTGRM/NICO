from nico.full_enterprise_production_binding_v4 import enrich_full_enterprise_output


def test_full_enterprise_output_is_bound_and_fail_closed() -> None:
    payload = {
        "sections": [
            {
                "id": "architecture",
                "evidence": ["service inventory"],
                "findings": ["Ownership concentration requires review."],
            }
        ],
        "repair_intelligence": {
            "candidates": [
                {
                    "title": "Ownership concentration requires review.",
                    "severity": "high",
                    "confidence": "high",
                    "business_impact": "Release continuity is concentrated.",
                    "technical_impact": "Critical knowledge has insufficient redundancy.",
                    "root_cause": "Secondary ownership is not proven.",
                    "recommended_action": "Assign and validate a secondary owner.",
                    "owner": "Engineering leadership",
                    "effort": "2-4 engineer-days",
                }
            ]
        },
    }
    enriched = enrich_full_enterprise_output(payload)
    binding = enriched["full_enterprise_production_binding"]
    assert binding["production_bound"] is True
    assert binding["pdf_bound"] is True
    assert binding["html_bound"] is True
    assert binding["markdown_bound"] is True
    assert binding["minimum_pages"] == 70
    assert binding["maximum_pages"] == 120
    assert binding["target_pages"] == 90
    assert binding["visual_count"] == 22
    assert binding["dossier_count"] == 1
    assert enriched["human_review_required"] is True
    assert enriched["client_ready"] is False
    assert enriched["full_enterprise_dossiers"]["records"][0]["approval_required"] is True
