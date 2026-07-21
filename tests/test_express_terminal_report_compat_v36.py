from __future__ import annotations

from nico.express_terminal_report_compat_v36 import VERSION, install_express_terminal_report_compat_v36


def test_compat_installer_is_bound_and_preserves_legacy_scores() -> None:
    install_express_terminal_report_compat_v36()
    from nico import express_terminal_report_truth_v34 as terminal

    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 82},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "yellow",
                "score": 74,
                "summary": "Review limited.",
                "evidence": [],
                "findings": ["This section cannot claim GREEN 90 until evidence is complete."],
                "unavailable": [],
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "status": "gray",
                "score": 0,
                "summary": "Pending.",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            },
        ],
        "quick_wins": ["Make the next service tier as easy as Express."],
        "medium_term_plan": ["One-click Mid Technical Health Assessment workflow."],
        "reports": {},
    }

    terminal._finalize_result_truth(result)
    markdown = terminal.build_presentation_markdown(result)

    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    assert dependency["presented_score"] == 74
    assert dependency["presented_status"] == "yellow"
    assert "Dependency / Library Ecosystem — YELLOW (74/100)" in markdown
    assert "GREEN 90" not in markdown
    assert "Make the next service tier as easy as Express" in markdown
    assert "One-click Mid Technical Health Assessment workflow" in markdown
    assert result["express_terminal_report_truth"]["authoritative_current_run_scoring"] is False
    assert VERSION == "nico.express_terminal_report_compat.v36"


def test_exact_snapshot_status_records_enable_evidence_specific_deductions() -> None:
    install_express_terminal_report_compat_v36()
    from nico import express_terminal_report_truth_v34 as terminal

    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 90},
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 90,
                "summary": "Current-run static evidence.",
                "evidence": [
                    "Exact-snapshot bandit status=failed; findings=0; commit=" + "b" * 40 + "; scan_id=scan_snapshot_001."
                ],
                "findings": ["Bandit ended with status failed; review required."],
                "unavailable": [],
            }
        ],
        "reports": {},
    }

    terminal._finalize_result_truth(result)
    section = result["sections"][0]

    assert section["source_score"] == 90
    assert section["presented_score"] < 90
    assert section["presented_status"] == "yellow"
    assert any(item["rule_id"] == "ANALYZER_FAILURE" for item in section["score_deductions"])
    assert result["express_terminal_report_truth"]["authoritative_current_run_scoring"] is True
