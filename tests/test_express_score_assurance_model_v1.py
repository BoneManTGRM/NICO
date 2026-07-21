from __future__ import annotations

from copy import deepcopy

from nico.express_section_status_truth_v26 import reconcile_section_status_truth


def _section(score: int, status: str, *, section_id: str = "ci_cd") -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "presented_score": score,
        "status": status,
        "evidence": [],
        "findings": [],
        "unavailable": [],
    }


def test_high_yellow_score_is_exceptional_but_review_limited() -> None:
    result = reconcile_section_status_truth({"sections": [_section(92, "yellow")]})
    section = result["sections"][0]
    assert section["technical_score_display"] == "EXCEPTIONAL · 92/100"
    assert section["score_tone"] == "green"
    assert section["assurance_display"] == "REVIEW LIMITED"
    assert section["assurance_tone"] == "yellow"
    assert section["status"] == "yellow"


def test_strong_yellow_score_keeps_review_limited_assurance() -> None:
    result = reconcile_section_status_truth({"sections": [_section(87, "yellow")]})
    section = result["sections"][0]
    assert section["score_band"] == "strong"
    assert section["score_band_label"] == "STRONG"
    assert section["assurance_status"] == "review_limited"


def test_moderate_yellow_score_is_not_mislabeled_strong() -> None:
    result = reconcile_section_status_truth({"sections": [_section(72, "yellow")]})
    section = result["sections"][0]
    assert section["technical_score_display"] == "MODERATE · 72/100"
    assert section["score_tone"] == "yellow"
    assert section["assurance_display"] == "REVIEW LIMITED"


def test_green_86_is_strong_and_verified() -> None:
    result = reconcile_section_status_truth({"sections": [_section(86, "green", section_id="code_audit")]})
    section = result["sections"][0]
    assert section["technical_score_display"] == "STRONG · 86/100"
    assert section["assurance_display"] == "VERIFIED"
    assert section["score_tone"] == "green"
    assert section["assurance_tone"] == "green"


def test_supplemental_and_pending_acceptance_remain_not_scored() -> None:
    result = reconcile_section_status_truth(
        {
            "sections": [
                _section(18, "red", section_id="scanner_worker_evidence"),
                _section(0, "gray", section_id="client_acceptance"),
            ],
            "client_acceptance": {"status": "pending"},
        }
    )
    scanner, acceptance = result["sections"]
    assert scanner["technical_score_display"] == "NOT SCORED"
    assert scanner["assurance_display"] == "SUPPLEMENTAL"
    assert acceptance["technical_score_display"] == "NOT SCORED"
    assert acceptance["assurance_display"] == "HUMAN REVIEW PENDING"


def test_input_remains_immutable() -> None:
    source = {"sections": [_section(92, "yellow")]}
    before = deepcopy(source)
    reconcile_section_status_truth(source)
    assert source == before
