from __future__ import annotations

import io
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_report_clarity_v1 import (
    assert_comprehensive_report_clarity,
    install_comprehensive_report_clarity,
    normalize_comprehensive_report_clarity,
)
from nico.v2_client_ready_truth_projection_v1 import _provisional_sections


ROOT = Path(__file__).resolve().parents[1]
DISCLOSURE = (
    "Confirmed material findings: 0. "
    "Review-required candidates: {count}. "
    "Score effect: assurance-only until triaged."
)


def _candidate_section(
    section_id: str,
    label: str,
    count: int,
    summary: str,
) -> dict:
    return {
        "id": section_id,
        "label": label,
        "score": 96,
        "presented_score": 96,
        "source_score": 96,
        "status": "strong",
        "status_label": "Provisional Strong",
        "presented_status": "STRONG",
        "summary": summary + " " + " ".join(
            DISCLOSURE.format(count=count) for _ in range(4)
        ),
        "evidence": [
            "Applicable analyzers: exact tools.",
            f"Raw candidates: {count}.",
            "Verified material: 0.",
            f"Review required: {count}.",
            "Approved/nonblocking: 0.",
            "Technical-score impact is limited to verified material findings and incomplete applicable analyzer execution.",
        ],
        "unavailable": [
            f"{count} unverified candidate(s) remain review-required; "
            "candidate volume affects assurance only and is not scored as confirmed defect volume."
        ],
        "confirmed_material_findings": 0,
        "review_required_candidates": count,
        "score_effect": "assurance-only until triaged",
        "score_contract": {
            "material_count": 0,
            "review_required_count": count,
            "unverified_candidate_volume_affects_technical_score": False,
        },
    }


def _canonical(*, spanish: bool = False, hotspots: int = 50) -> dict:
    language = "es-MX" if spanish else "en"
    architecture_hotspots = [
        {
            "finding_id": f"NICO-CODE-{index:04d}",
            "finding_family": "complexity_hotspot",
            "location": f"nico/module_{index}.py:{index + 10}",
            "path": f"nico/module_{index}.py",
            "line": index + 10,
        }
        for index in range(hotspots)
    ]
    sections = [
        _candidate_section(
            "dependency_health",
            "Dependency / Library Ecosystem",
            59,
            "Dependency evidence was reconciled.",
        ),
        _candidate_section(
            "secrets_review",
            "Secrets Exposure Review",
            17,
            "Secret evidence was classified.",
        ),
        _candidate_section(
            "static_analysis",
            "Static Analysis",
            581,
            "Static-analysis evidence was evaluated.",
        ),
        {
            "id": "architecture_debt",
            "label": "Architecture & Technical Debt",
            "score": 78,
            "presented_score": 78,
            "source_score": 78,
            "status": "moderate",
            "presented_status": "MODERATE",
            "summary": "Measured complexity evidence was evaluated.",
            "evidence": [
                "Source files: 864.",
                "Files analyzed for complexity: 865.",
                "Complexity risk: unknown.",
            ],
            "unavailable": [],
        },
    ]
    return {
        "report_language": language,
        "identity": {
            "report_language": language,
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_clarity",
        },
        "architecture_hotspots": architecture_hotspots,
        "assessment": {
            "report_language": language,
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 90,
            "maturity_signal": {
                "technical_score": 93,
                "presented_score": 93,
            },
            "architecture_hotspots": architecture_hotspots,
            "sections": sections,
        },
        "review_candidate_summary": {
            "by_category": {
                "dependency": {"material": 0, "review_required": 59},
                "secret": {"material": 0, "review_required": 17},
                "static": {"material": 0, "review_required": 581},
            }
        },
    }


def _pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    y = 780
    for line in text.splitlines():
        document.drawString(36, y, line[:110])
        y -= 14
        if y < 40:
            document.showPage()
            y = 780
    document.save()
    return buffer.getvalue()


def _rendered_text(canonical: dict) -> str:
    lines: list[str] = ["AUTOMATED DRAFT", "CLIENT DELIVERY BLOCKED"]
    for section in canonical["assessment"]["sections"]:
        lines.append(
            f"{section['label']} — {section.get('presented_status')} — "
            f"{section.get('presented_score')}/100"
        )
        lines.append(section.get("summary", ""))
        lines.extend(section.get("evidence", []))
        lines.extend(section.get("unavailable", []))
    return "\n".join(lines)


def test_projection_is_idempotent_and_sets_client_facing_review_status() -> None:
    canonical = _canonical()
    summary = canonical["review_candidate_summary"]
    before_scores = [
        (item["id"], item["score"], item["presented_score"])
        for item in canonical["assessment"]["sections"]
    ]

    for _ in range(4):
        _provisional_sections(canonical, summary)

    sections = {
        item["id"]: item for item in canonical["assessment"]["sections"]
    }
    for section_id in ("dependency_health", "secrets_review", "static_analysis"):
        section = sections[section_id]
        assert "Confirmed material findings:" not in section["summary"]
        assert (
            section["presented_status"]
            == "Provisional Strong — Human Review Required"
        )
    after_scores = [
        (item["id"], item["score"], item["presented_score"])
        for item in canonical["assessment"]["sections"]
    ]
    assert before_scores == after_scores


def test_clarity_normalization_deduplicates_and_reconciles_complexity_truth() -> None:
    canonical = _canonical()
    result = normalize_comprehensive_report_clarity(canonical)
    sections = {
        item["id"]: item for item in result["assessment"]["sections"]
    }

    assert result["assessment"]["technical_score"] == 93
    assert result["assessment"]["canonical_evidence_adjusted_score"] == 90
    for section_id, count in (
        ("dependency_health", 59),
        ("secrets_review", 17),
        ("static_analysis", 581),
    ):
        section = sections[section_id]
        assert section["score"] == 96
        assert section["presented_score"] == 96
        assert section["source_score"] == 96
        assert "Confirmed material findings:" not in section["summary"]
        assert (
            section["presented_status"]
            == "Provisional Strong — Human Review Required"
        )
        assert section["evidence"].count(
            "Confirmed material findings: 0."
        ) == 1
        assert section["evidence"].count(
            f"Review-required candidates: {count}."
        ) == 1
        assert section["evidence"].count(
            "Score effect: assurance-only until triaged."
        ) == 1
        assert not section["unavailable"]

    architecture = sections["architecture_debt"]
    assert architecture["score"] == 78
    assert architecture["exact_source_complexity_finding_count"] == 50
    assert "Complexity risk: unknown." not in architecture["evidence"]
    assert (
        "Complexity risk: observed; 50 exact-source complexity findings "
        "remain pending human review."
        in architecture["evidence"]
    )


def test_clarity_normalization_is_idempotent() -> None:
    once = normalize_comprehensive_report_clarity(_canonical())
    twice = normalize_comprehensive_report_clarity(once)
    assert once == twice


def test_final_clarity_gate_accepts_clean_cross_format_surfaces() -> None:
    canonical = normalize_comprehensive_report_clarity(_canonical())
    text = _rendered_text(canonical)
    assert_comprehensive_report_clarity(
        canonical,
        text,
        f"<html><body>{text}</body></html>",
        _pdf(text),
    )


def test_final_clarity_gate_rejects_repeated_candidate_summary() -> None:
    canonical = normalize_comprehensive_report_clarity(_canonical())
    canonical["assessment"]["sections"][0]["summary"] += " " + DISCLOSURE.format(
        count=59
    )
    text = _rendered_text(canonical)
    with pytest.raises(ValueError, match="repeated assurance disclosure"):
        assert_comprehensive_report_clarity(
            canonical,
            text,
            text,
            _pdf(text),
        )


def test_final_clarity_gate_rejects_stale_strong_presented_status() -> None:
    canonical = normalize_comprehensive_report_clarity(_canonical())
    canonical["assessment"]["sections"][2]["presented_status"] = "STRONG"
    text = _rendered_text(canonical)
    with pytest.raises(ValueError, match="provisional human-review"):
        assert_comprehensive_report_clarity(
            canonical,
            text,
            text,
            _pdf(text),
        )


def test_final_clarity_gate_rejects_unknown_complexity_with_retained_hotspots() -> None:
    canonical = normalize_comprehensive_report_clarity(_canonical())
    architecture = canonical["assessment"]["sections"][3]
    architecture["evidence"] = ["Complexity risk: unknown."]
    text = _rendered_text(canonical)
    with pytest.raises(ValueError, match="unknown complexity"):
        assert_comprehensive_report_clarity(
            canonical,
            text,
            text,
            _pdf(text),
        )


def test_no_hotspot_count_is_not_invented() -> None:
    canonical = normalize_comprehensive_report_clarity(_canonical(hotspots=0))
    architecture = canonical["assessment"]["sections"][3]
    assert architecture["evidence"] == [
        "Source files: 864.",
        "Files analyzed for complexity: 865.",
        "Complexity risk: unknown.",
    ]
    text = _rendered_text(canonical)
    assert_comprehensive_report_clarity(
        canonical,
        text,
        text,
        _pdf(text),
    )


def test_spanish_status_is_explicitly_review_gated() -> None:
    canonical = normalize_comprehensive_report_clarity(_canonical(spanish=True))
    static = canonical["assessment"]["sections"][2]
    assert (
        static["presented_status"]
        == "Fuerte provisional — Revisión humana requerida"
    )


def test_installation_binds_all_authoritative_completion_surfaces() -> None:
    state = install_comprehensive_report_clarity()
    assert state["canonical_sync_bound"] is True
    assert state["scanner_reconciliation_bound"] is True
    assert state["final_surface_gate_bound"] is True
    assert state["scores_unchanged"] is True
    assert state["scanner_dispositions_unchanged"] is True
    assert state["human_review_required"] is True
    assert state["client_delivery_allowed"] is False


def test_phase17_installs_clarity_before_compact_design_gate() -> None:
    source = (
        ROOT / "nico" / "phase17_canonical_artifact_rebuild_v1.py"
    ).read_text(encoding="utf-8")
    assert source.index(
        "_REPORT_CLARITY = install_comprehensive_report_clarity()"
    ) < source.index(
        "_COMPACT_DESIGN_MARKER_GATE = install_compact_design_marker_gate()"
    )
