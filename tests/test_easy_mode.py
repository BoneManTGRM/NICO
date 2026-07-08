from nico.easy_mode import build_easy_mode_catalog, build_easy_mode_intake
from nico.service_catalog_api import easy_mode_intake_response, easy_mode_response, EasyModeIntakeRequest


def test_easy_mode_catalog_maps_all_major_sections_to_express_pattern():
    catalog = build_easy_mode_catalog()

    assert catalog["status"] == "ok"
    workflows = {item["workflow"] for item in catalog["workflow_cards"]}
    assert {"express", "scanner_worker", "mid", "retainer", "reports"}.issubset(workflows)
    assert any("Do not invent" in item for item in catalog["guardrails"])
    assert any("Easy Full Run" in item for item in catalog["next_engineering_updates"])


def test_easy_mode_intake_seeds_mid_and_retainer_without_claiming_proof():
    payload = {
        "repository": "BoneManTGRM/NICO",
        "client_name": "Bernardo",
        "project_name": "NICO",
        "findings": ["Dependency evidence is missing scanner-clean proof."],
        "repairs": ["Run pip-audit and attach the artifact."],
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "yellow",
                "score": 74,
                "summary": "Dependency review is not scanner-clean.",
                "findings": ["pip-audit artifact missing"],
                "unavailable": ["OSV Scanner missing"],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "yellow",
                "score": 74,
                "summary": "Bandit findings require review.",
                "findings": ["50 Bandit findings need triage"],
                "unavailable": ["Semgrep missing"],
            },
        ],
    }

    intake = build_easy_mode_intake(payload)

    assert intake["status"] == "ok"
    assert intake["repository"] == "BoneManTGRM/NICO"
    assert "Dependency evidence is missing" in intake["mid_prefill"]["qa_evidence"]
    assert "Dependency / Library Ecosystem" in intake["mid_prefill"]["roadmap_notes"]
    assert "Static Analysis" in intake["retainer_prefill"]["blockers"]
    assert "Seeded text is workflow guidance" in intake["guardrail"]


def test_service_catalog_easy_mode_endpoints_are_callable():
    assert easy_mode_response()["mode"] == "guided_easy_mode"
    result = easy_mode_intake_response(EasyModeIntakeRequest(payload={"repository": "owner/repo"}))
    assert result["repository"] == "owner/repo"
