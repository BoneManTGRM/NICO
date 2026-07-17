from nico.mid_report_premium_contract_v8 import (
    MAX_PAGES,
    MIN_PAGES,
    TARGET_PAGES,
    mid_report_contract,
    reconcile_mid_scores,
)


def _fixture() -> dict:
    return {
        "sections": [
            {
                "id": "architecture",
                "label": "Architecture",
                "score": 92,
                "summary": "Architecture evidence is retained.",
                "evidence": ["Exact architecture inventory."],
                "findings": ["One architecture issue requires review."],
                "unavailable": [],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 88,
                "summary": "Bandit failed and Semgrep requires human triage.",
                "evidence": ["Semgrep artifact retained."],
                "findings": ["Semgrep finding requires human triage."],
                "unavailable": ["Bandit failed during execution."],
            },
        ]
    }


def test_mid_scores_are_fail_closed_when_evidence_is_unresolved() -> None:
    result = _fixture()
    records = reconcile_mid_scores(result)
    architecture = next(item for item in records if item.section_id == "architecture")
    static = next(item for item in records if item.section_id == "static_analysis")
    assert architecture.presented_score <= 74
    assert architecture.status != "green"
    assert static.presented_score <= 74
    assert static.status != "green"
    assert static.deductions


def test_mid_contract_enforces_35_to_50_substantive_pages() -> None:
    result = _fixture()
    contract = mid_report_contract(result, "en-US")
    assert contract["page_contract"] == {
        "minimum": MIN_PAGES,
        "target": TARGET_PAGES,
        "maximum": MAX_PAGES,
    }
    assert MIN_PAGES == 35
    assert TARGET_PAGES == 42
    assert MAX_PAGES == 50
    assert contract["minimum_visuals"] == 10
    assert contract["maximum_visuals"] == 15
    assert contract["full_finding_dossiers_required"] is True
    assert contract["client_delivery_allowed"] is False


def test_mid_english_and_spanish_contracts_have_identical_structure() -> None:
    english_result = _fixture()
    spanish_result = _fixture()
    english = mid_report_contract(english_result, "en-US")
    spanish = mid_report_contract(spanish_result, "es-MX")
    assert set(english) == set(spanish)
    assert len(english["required_sections"]) == len(spanish["required_sections"])
    assert english["page_contract"] == spanish["page_contract"]
    assert english["score_record_count"] == spanish["score_record_count"]
    assert english["labels"]["title"] != spanish["labels"]["title"]
    assert spanish["labels"]["review"] == "Se requiere revisión humana"
