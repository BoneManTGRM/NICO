from nico.full_report_premium_contract_v1 import (
    MAX_PAGES,
    MAX_VISUALS,
    MIN_PAGES,
    MIN_VISUALS,
    TARGET_PAGES,
    full_report_contract,
    reconcile_full_scores,
)


def _fixture() -> dict:
    return {
        "sections": [
            {
                "id": "architecture",
                "label": "Architecture",
                "score": 94,
                "summary": "Architecture evidence is retained.",
                "evidence": ["Exact architecture inventory."],
                "findings": ["One architecture issue requires review."],
                "unavailable": [],
            },
            {
                "id": "resilience",
                "label": "Resilience",
                "score": 91,
                "summary": "Recovery evidence is incomplete and one analyzer timed out.",
                "evidence": ["Recovery checklist retained."],
                "findings": ["Disaster recovery evidence requires human triage."],
                "unavailable": ["Failover analyzer timed out."],
            },
        ]
    }


def test_full_scores_fail_closed_when_evidence_is_unresolved() -> None:
    result = _fixture()
    records = reconcile_full_scores(result)
    architecture = next(item for item in records if item.section_id == "architecture")
    resilience = next(item for item in records if item.section_id == "resilience")
    assert architecture.presented_score <= 74
    assert architecture.status != "green"
    assert resilience.presented_score <= 74
    assert resilience.status != "green"
    assert resilience.deductions


def test_full_contract_enforces_enterprise_depth_and_visuals() -> None:
    result = _fixture()
    contract = full_report_contract(result, "en-US")
    assert contract["page_contract"] == {
        "minimum": MIN_PAGES,
        "target": TARGET_PAGES,
        "maximum": MAX_PAGES,
    }
    assert MIN_PAGES == 70
    assert TARGET_PAGES == 90
    assert MAX_PAGES == 120
    assert contract["visual_contract"] == {
        "minimum": MIN_VISUALS,
        "maximum": MAX_VISUALS,
    }
    assert MIN_VISUALS == 20
    assert MAX_VISUALS == 30
    assert contract["full_finding_dossiers_required"] is True
    assert contract["budget_and_resource_plan_required"] is True
    assert contract["stakeholder_interview_layer_required"] is True
    assert contract["client_delivery_allowed"] is False


def test_full_english_and_spanish_contracts_have_identical_structure() -> None:
    english = full_report_contract(_fixture(), "en-US")
    spanish = full_report_contract(_fixture(), "es-MX")
    assert set(english) == set(spanish)
    assert english["page_contract"] == spanish["page_contract"]
    assert english["visual_contract"] == spanish["visual_contract"]
    assert len(english["required_sections"]) == len(spanish["required_sections"])
    assert english["score_record_count"] == spanish["score_record_count"]
    assert english["labels"]["title"] != spanish["labels"]["title"]
    assert spanish["labels"]["review"] == "Se requiere revisión humana"
