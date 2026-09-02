from __future__ import annotations

import io

from pypdf import PdfReader

from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY
from nico.comprehensive_decision_grade_pdf_v5 import _supplement_pdf
from nico.comprehensive_premium_pdf_v6 import _build_pdf
from nico.v2_automated_draft_quality_compat_v1 import (
    _contains_legacy_bare_draft,
    _validate_review_pdf,
)


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_comprehensive_report_lists_do_not_extract_as_control_characters() -> None:
    identity = {
        "repository": "example/repository",
        "commit_sha": "a" * 40,
        "run_id": "comprun_text_safety",
        "evidence_ledger_id": "ledger_text_safety",
    }
    assessment = {
        "maturity_signal": {"score": 84, "presented_score": 84, "score_band_label": "STRONG"},
        "sections": [
            {
                "id": "architecture_debt",
                "label": "Architecture and Complexity",
                "score_value": 84,
                "evidence": ["Source files: 10."],
                "findings": ["One hotspot requires review."],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD",
                "technical_score_display": "84/100",
                "assurance_label": "REVIEW LIMITED",
                "summary": "Workflow evidence was reviewed.",
                "evidence": ["Workflow files: 2."],
                "findings": [],
                "unavailable": ["One historical run requires classification."],
            },
        ],
        "findings_register": [],
        "executive_risk_register": [],
        "scoring_weights": [],
    }
    stages = [
        {
            "stage_id": "technical_analysis",
            "title": "Technical analysis",
            "status": "complete",
            "summary": "Bounded evidence was retained.",
            "evidence": ["Stage evidence item."],
            "findings": ["Stage finding item."],
            "unavailable": ["Stage limitation item."],
        }
    ]

    text = _pdf_text(
        _build_pdf(
            identity,
            assessment,
            stages,
            roadmap=[],
            staffing=[],
            limitations={"individual_limitation_records": 2},
            generated_at="2026-07-24T00:00:00Z",
        )
    )

    assert "\x7f" not in text
    assert "- Source files: 10." in text
    assert "- Workflow files: 2." in text
    assert "- Stage evidence item." in text


def _boundary_pdf(
    report_language: str,
) -> tuple[bytes, str, dict[str, str], dict[str, object]]:
    identity = {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "b" * 40,
        "run_id": "comprun_approved_draft_boundary",
        "evidence_ledger_id": "ledger_approved_draft_boundary",
        "report_language": report_language,
    }
    assessment = {
        "maturity_signal": {
            "score": 93,
            "presented_score": 93,
            "score_band_label": "STRONG",
        },
        "sections": [],
        "findings_register": [],
        "executive_risk_register": [],
        "scoring_weights": [],
    }
    pdf = _build_pdf(
        identity,
        assessment,
        [],
        roadmap=[],
        staffing=[],
        limitations={"individual_limitation_records": 0},
        generated_at="2026-09-02T00:00:00Z",
    )
    return pdf, _pdf_text(pdf), identity, assessment


def test_comprehensive_report_uses_approved_automated_draft_boundary() -> None:
    pdf, text, identity, assessment = _boundary_pdf("en")

    assert EN_BOUNDARY in text
    assert _contains_legacy_bare_draft(text) is False
    assert identity["run_id"] in text
    assert identity["commit_sha"] in text
    _validate_review_pdf(
        pdf,
        {"identity": identity, "assessment": assessment},
        expected_sections=[],
        spanish=False,
    )


def test_comprehensive_report_localizes_approved_draft_boundary_to_spanish() -> None:
    pdf, text, identity, assessment = _boundary_pdf("es-MX")

    assert ES_BOUNDARY in text
    assert _contains_legacy_bare_draft(text) is False
    _validate_review_pdf(
        pdf,
        {"identity": identity, "assessment": assessment},
        expected_sections=[],
        spanish=True,
    )


def test_comprehensive_supplement_lists_do_not_extract_as_control_characters() -> None:
    pdf_bytes = _supplement_pdf(
        [
            {
                "stage_id": "supplement",
                "title": "Supplement evidence",
                "status": "complete",
                "summary": "Supplement summary.",
                "evidence": ["Supplement evidence item."],
                "findings": ["Supplement finding item."],
                "unavailable": ["Supplement limitation item."],
            }
        ],
        pages_needed=1,
        run_id="comprun_supplement_text_safety",
    )
    text = _pdf_text(pdf_bytes)

    assert "\x7f" not in text
    assert "- Supplement evidence item." in text
    assert "- Supplement finding item." in text
    assert "- Supplement limitation item." in text
