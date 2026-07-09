from __future__ import annotations

import json

from nico.report_full_detail_export_patch import attach_full_detail_report_exports, build_full_detail_export, install_report_full_detail_export_patch


def result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T22:00:00Z",
        "assessment_mode": "express",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 82,
                "status": "yellow",
                "summary": "Static scanner evidence attached.",
                "evidence": ["Bandit completed.", "Semgrep unavailable."],
                "findings": ["Bandit B602 needs review."],
                "unavailable": ["ESLint project commands disabled."],
            }
        ],
        "scanner_worker_artifact": {
            "tools": {
                "bandit": {"status": "completed", "current_run": True, "verified_for_this_report": True, "findings_count": 1},
                "eslint": {"status": "unavailable", "current_run": True, "verified_for_this_report": False, "reason": "Project commands disabled."},
            }
        },
        "evidence_ledger": {
            "entry_count": 4,
            "verified_entry_count": 1,
            "partial_entry_count": 1,
            "unavailable_entry_count": 1,
            "finding_entry_count": 1,
            "ledger_hash": "abc123",
        },
        "reports": {"markdown": "# Report\n", "html": "<html></html>"},
        "human_review_required": True,
    }


def test_build_full_detail_export_preserves_full_section_detail():
    detail = build_full_detail_export(result())

    assert detail["artifact_schema"] == "nico.report_full_detail.v1"
    assert detail["section_count"] == 1
    assert detail["sections"][0]["evidence_count"] == 2
    assert detail["sections"][0]["finding_count"] == 1
    assert detail["sections"][0]["unavailable_count"] == 1
    assert detail["scanner_worker_artifact_summary"]["tools"]["bandit"]["verified_for_this_report"] is True
    assert detail["evidence_ledger_summary"]["ledger_hash"] == "abc123"


def test_attach_full_detail_report_exports_adds_json_markdown_and_html():
    output = attach_full_detail_report_exports(result())

    assert output["reports"]["full_detail_filename"].endswith(".json")
    assert output["reports"]["full_detail_markdown_filename"].endswith(".md")
    parsed = json.loads(output["reports"]["full_detail_json"])
    assert parsed["repository"] == "BoneManTGRM/NICO"
    assert "## Full Evidence Detail Appendix" in output["reports"]["markdown"]
    assert "Full Evidence Detail Appendix" in output["reports"]["html"]
    assert output["report_full_detail_export"]["artifact_schema"] == "nico.report_full_detail.v1"


def test_full_detail_patch_increases_pdf_bullet_limit(monkeypatch):
    from nico import assessment_quality

    install_report_full_detail_export_patch()
    captured = {}

    def fake_original(items, style, max_items=6):
        captured["max_items"] = max_items
        return []

    monkeypatch.setattr(assessment_quality, "_nico_original_bullets_for_full_detail", fake_original)
    assessment_quality._bullets(["one", "two", "three", "four"], object(), max_items=2)

    assert captured["max_items"] == 4
