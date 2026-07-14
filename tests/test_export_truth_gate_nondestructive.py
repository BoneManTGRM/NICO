from __future__ import annotations

from nico.export_truth_gate import apply_export_truth_gate
from nico.trust_report_display import attach_trust_report_display


def test_export_truth_gate_preserves_artifacts_for_review_warnings() -> None:
    result = {
        "status": "complete",
        "maturity_signal": {"score": 89, "level": "Senior"},
        "reports": {
            "markdown": "SCORE 89/100\n\n### Velocity / Complexity — GREEN 90/100\nrelease-readiness missing complexity proof",
            "html": "<h3>Velocity / Complexity - GREEN 90/100</h3><p>release-readiness missing complexity proof</p>",
            "pdf_base64": "ZmFrZS1wZGY=",
        },
        "sections": [
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "status": "green",
                "score": 90,
                "summary": "release-readiness missing complexity proof",
                "evidence": ["release-readiness missing complexity proof"],
                "findings": [],
                "unavailable": [],
            }
        ],
    }

    updated = apply_export_truth_gate(result)

    assert updated["export_truth_gate"]["status"] == "review_required"
    assert updated["export_truth_gate"]["export_allowed"] is True
    assert updated["export_truth_gate"]["draft_only"] is True
    assert updated["reports"]["markdown"].startswith("SCORE 89/100")
    assert updated["reports"]["html"].startswith("<h3>")
    assert updated["reports"]["pdf_base64"] == "ZmFrZS1wZGY="
    assert updated["client_ready"] is False


def test_trust_display_treats_export_review_as_pending_not_red() -> None:
    result = apply_export_truth_gate(
        {
            "status": "complete",
            "maturity_signal": {"score": 89, "level": "Senior"},
            "reports": {
                "markdown": "SCORE 89/100\n\n### Velocity / Complexity — GREEN 90/100\nrelease-readiness missing complexity proof",
                "html": "<h3>Velocity / Complexity - GREEN 90/100</h3><p>release-readiness missing complexity proof</p>",
                "pdf_base64": "ZmFrZS1wZGY=",
            },
            "sections": [
                {
                    "id": "velocity_complexity",
                    "label": "Velocity / Complexity",
                    "status": "green",
                    "score": 90,
                    "summary": "release-readiness missing complexity proof",
                    "evidence": ["release-readiness missing complexity proof"],
                    "findings": [],
                    "unavailable": [],
                }
            ],
        }
    )

    displayed = attach_trust_report_display(result)
    trust = displayed["sections"][0]

    assert trust["id"] == "trust_readiness"
    assert trust["status"] == "pending"
    assert trust["workflow_state"] == "review_required"
    assert trust["status_semantics"] == "review_workflow_state"
    assert "Review-limited" in trust["summary"]
    assert any("draft-only" in item for item in trust["findings"])
