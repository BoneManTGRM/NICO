from __future__ import annotations

import io

from pypdf import PdfReader

from nico.comprehensive_decision_grade_pdf_v5 import _supplement_pdf
from nico.comprehensive_premium_pdf_v6 import _build_pdf


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
