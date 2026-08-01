from __future__ import annotations

from nico.comprehensive_scoring_manifest_v54 import (
    assurance_factor,
    enrich_scoring_rows,
    install_comprehensive_scoring_manifest_v54,
)


def test_assurance_factor_mapping_is_deterministic() -> None:
    assert assurance_factor("VERIFIED") == ("verified", 1.0)
    assert assurance_factor("Partial") == ("partial", 0.98)
    assert assurance_factor("REVIEW LIMITED") == ("review_limited", 0.95)
    assert assurance_factor("BLOCKED") == ("blocked", 0.85)


def test_scoring_rows_retain_numeric_factor_from_section_truth() -> None:
    rows = [
        {
            "section_id": "static_analysis",
            "technical_score": 85,
            "weight": 0.15,
            "assurance": "REVIEW LIMITED",
            "included": True,
        },
        {
            "section_id": "platform_parity",
            "technical_score": None,
            "weight": 0.0,
            "included": False,
        },
    ]
    sections = [
        {
            "id": "static_analysis",
            "assurance_status": "review_limited",
            "assurance_label": "REVIEW LIMITED",
        }
    ]

    enriched = enrich_scoring_rows(rows, sections)

    assert enriched[0]["assurance_status"] == "review_limited"
    assert enriched[0]["assurance_factor"] == 0.95
    assert enriched[1]["assurance_factor"] is None


def test_runtime_installer_is_idempotent() -> None:
    first = install_comprehensive_scoring_manifest_v54()
    second = install_comprehensive_scoring_manifest_v54()

    assert first["bound"] is True
    assert second["bound"] is True
    assert second["status"] == "already_installed"
