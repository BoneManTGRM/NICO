from __future__ import annotations

from pathlib import Path

from nico.express_terminal_report_truth_v34 import (
    VERSION,
    build_presentation_markdown,
    install_express_terminal_report_truth_v34,
    normalize_section_aliases,
)


ROOT = Path(__file__).resolve().parents[1]


def test_scanner_worker_alias_and_pending_acceptance_are_not_scored() -> None:
    result = {
        "sections": [
            {
                "id": "scanner_worker",
                "label": "Scanner Worker Evidence",
                "score": 9,
                "status": "supplemental",
                "evidence": ["Scanner worker result retained."],
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
            },
        ]
    }

    normalize_section_aliases(result)
    by_id = {section["id"]: section for section in result["sections"]}

    assert set(by_id) == {"scanner_worker_evidence", "client_acceptance"}
    for section in by_id.values():
        assert section["score"] is None
        assert section["presented_score"] is None
        assert section["directly_scored"] is False
        assert section["score_label"] == "NOT SCORED"
    assert by_id["scanner_worker_evidence"]["diagnostic_source_score"] == 9


def test_authoritative_current_run_semgrep_record_overrides_stale_unavailable_narrative() -> None:
    install_express_terminal_report_truth_v34()
    from nico.express_scanner_disposition_truth_v1 import reconcile_express_scanner_dispositions

    result = {
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 90,
                "status": "yellow",
                "evidence": [
                    "Exact-snapshot semgrep status=completed; findings=69; commit=" + "a" * 40 + "; scan_id=scan_snapshot_001.",
                ],
                "findings": [],
                "unavailable": [
                    "Semgrep exact-snapshot analyzer unavailable for this run.",
                ],
            }
        ]
    }

    reconcile_express_scanner_dispositions(result)
    section = result["sections"][0]
    disposition = section["scanner_dispositions"]["semgrep"]

    assert disposition["status"] == "completed_findings"
    assert disposition["findings"] == 69
    assert not any("semgrep" in str(item).casefold() for item in section.get("unavailable") or [])
    assert any(
        "Canonical scanner disposition: semgrep=completed_with_candidates; candidates=69" in item
        for item in section["evidence"]
    )


def test_presentation_markdown_uses_adjusted_scores_and_never_none_over_100() -> None:
    result = {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-21T00:21:29Z",
        "client_name": "Cody Jenkins",
        "project_name": "NICO Audit",
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "maturity_signal": {"level": "Senior", "score": 90, "source_score": 90, "presented_score": 76},
        "evidence_adjusted_score": 76,
        "executive_summary": "Transparent summary.",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 90,
                "source_score": 90,
                "presented_score": 62,
                "status": "green",
                "presented_status": "yellow",
                "summary": "Review-limited static evidence.",
                "evidence": ["Bandit failed."],
                "findings": ["Human triage required."],
                "score_deductions": [
                    {
                        "rule_id": "ANALYZER_FAILURE",
                        "points": 10,
                        "reason": "A required analyzer failed.",
                        "evidence": "Bandit failed.",
                    }
                ],
            },
            {
                "id": "scanner_worker",
                "label": "Scanner Worker Evidence",
                "score": 9,
                "status": "supplemental",
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
            },
        ],
        "verification_checklist": ["Human review approves the exact snapshot."],
    }

    markdown = build_presentation_markdown(result)

    assert "Baseline source maturity: Senior (90/100)" in markdown
    assert "Evidence-adjusted score: 76/100" in markdown
    assert "### Static Analysis — YELLOW (62/100)" in markdown
    assert "### Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)" in markdown
    assert "### Client / Human Acceptance — GRAY (NOT SCORED)" in markdown
    assert "None/100" not in markdown
    assert "ANALYZER_FAILURE: -10 points" in markdown


def test_live_binding_installs_terminal_truth_pdf_parity_and_compatibility_last() -> None:
    source = (ROOT / "nico" / "express_live_renderer_binding_v22.py").read_text(encoding="utf-8")

    assert "install_express_terminal_report_truth_v34" in source
    assert "install_express_not_scored_pdf_append_v35" in source
    assert "install_express_terminal_report_compat_v36" in source
    assert source.index("client_report_postprocessor = install_express_client_report_postprocessor_v27()") < source.index(
        "terminal_report_truth = install_express_terminal_report_truth_v34()"
    )
    assert source.index("terminal_report_truth = install_express_terminal_report_truth_v34()") < source.index(
        "not_scored_pdf_append = install_express_not_scored_pdf_append_v35()"
    )
    assert source.index("not_scored_pdf_append = install_express_not_scored_pdf_append_v35()") < source.index(
        "terminal_report_compat = install_express_terminal_report_compat_v36()"
    )
    assert VERSION == "nico.express_terminal_report_truth.v34"
