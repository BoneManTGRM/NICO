from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.express_report_base_v13 import EXPRESS_BASE_REPORT_VERSION, build_express_base_pdf


def section(section_id: str, label: str, score: int, findings=None) -> dict:
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": "green",
        "summary": f"Summary for {label}.",
        "evidence": [f"Evidence {index} for {label}." for index in range(1, 7)],
        "findings": findings or [],
        "unavailable": [],
    }


def test_decision_summary_and_duplicate_suppression() -> None:
    duplicate = "Complexity and high churn overlap in 41 delivery hotspot file(s)."
    result = {
        "repository": "owner/repository",
        "client_name": "Client",
        "project_name": "Project",
        "generated_at": "2026-07-15T20:00:00Z",
        "executive_summary": "Evidence-bound assessment complete.",
        "maturity_signal": {"level": "Senior", "score": 92},
        "human_review_required": True,
        "sections": [
            section("code_audit", "Code Audit", 90),
            section("dependency_health", "Dependency Health", 90),
            section("architecture_debt", "Architecture & Technical Debt", 94, [duplicate]),
            section("velocity_complexity", "Velocity / Complexity", 90, [duplicate, "A unique velocity finding."]),
        ],
        "repair_intelligence": {
            "candidate_count": 2,
            "code_suggestion_count": 1,
            "candidates": [
                {"rank": 1, "title": "Runtime patch surface", "priority_score": 64.6},
                {"rank": 2, "title": "Branch inventory", "priority_score": 63.4},
            ],
            "advisories": [{"title": "Source-file footprint is planning context"}],
        },
        "repair_action_summary": {"top_actions": ["Consolidate runtime installers.", "Review branch retention policy."]},
        "medium_term_plan": ["Maintain scanner evidence."],
    }

    encoded, error = build_express_base_pdf(result)

    assert error is None
    pdf = base64.b64decode(encoded or "")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    normalized = " ".join(text.split())
    assert "express technical health assessment" in normalized.lower()
    assert "Decision Summary" in normalized
    assert "Highest-priority risks" in normalized
    assert "Immediate actions" in normalized
    assert "Verified controls" in normalized
    assert normalized.count(duplicate) == 1
    assert "A unique velocity finding" in normalized
    assert result["express_report_base"]["version"] == EXPRESS_BASE_REPORT_VERSION
    assert result["express_report_base"]["duplicate_finding_suppression"] is True
