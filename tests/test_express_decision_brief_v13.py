from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.express_decision_brief_v13 import (
    EXPRESS_DECISION_BRIEF_VERSION,
    build_express_with_decision_brief,
    install_express_decision_brief_v13,
)


def _base(_result: dict) -> tuple[str, None]:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.drawString(72, 720, "Existing professional Express report")
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def _result() -> dict:
    return {
        "maturity_signal": {"level": "Senior", "score": 92},
        "human_review_required": True,
        "evidence_coverage": {"calculated": True, "percent": 96},
        "sections": [
            {"id": "code_audit", "unavailable": []},
            {"id": "velocity_complexity", "unavailable": ["Stakeholder context requires review."]},
        ],
        "repair_action_summary": {
            "top_actions": [
                "Consolidate runtime installers in bounded migration slices.",
                "Apply a human-approved branch retention policy.",
            ]
        },
        "repair_intelligence": {
            "candidate_count": 2,
            "code_suggestion_count": 1,
            "advisories": [{"title": "Repository size context"}],
            "portfolio": {
                "severity_counts": {"critical": 0, "high": 1, "medium": 1, "low": 0, "info": 0}
            },
            "candidates": [
                {
                    "rank": 1,
                    "title": "Runtime patch surface creates import-order fragility",
                    "severity": "high",
                    "priority_score": 64.6,
                    "effort": "high",
                    "recommended_action": "Consolidate installers behind one explicit registry.",
                },
                {
                    "rank": 2,
                    "title": "Branch inventory increases maintenance cost",
                    "severity": "medium",
                    "priority_score": 53.4,
                    "effort": "medium",
                    "recommended_action": "Inventory active and protected branches before cleanup.",
                },
            ],
        },
    }


def test_express_decision_brief_is_first_page_and_preserves_base_report() -> None:
    result = _result()

    encoded, error = build_express_with_decision_brief(_base, result)

    assert error is None
    reader = PdfReader(io.BytesIO(base64.b64decode(encoded)))
    first = reader.pages[0].extract_text() or ""
    all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "NICO EXPRESS" in first
    assert "Executive decision brief" in first
    assert "Top actions" in first
    assert "Existing professional Express report" in all_text
    assert result["express_decision_brief"]["version"] == EXPRESS_DECISION_BRIEF_VERSION
    assert result["express_decision_brief"]["score_changed"] is False
    assert result["express_decision_brief"]["code_changes_applied"] is False


def test_express_decision_brief_installer_is_idempotent() -> None:
    first = install_express_decision_brief_v13()
    second = install_express_decision_brief_v13()

    assert first["executive_decision_brief"] is True or first["status"] == "already_installed"
    assert second["status"] == "already_installed"
