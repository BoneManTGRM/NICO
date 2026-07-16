from __future__ import annotations

from nico.mid_quality_issue_display_patch import apply_mid_quality_issue_display


def test_repeated_mid_quality_codes_are_labeled_by_section_without_weakening_block() -> None:
    result = {
        "status": "blocked",
        "report_generation_status": "blocked",
        "report_quality_issues": [
            {
                "severity": "critical",
                "code": "unsupported_section_conclusion",
                "section_id": "functional_qa",
                "message": "Section contains neither retained evidence nor an explicit unavailable-evidence disclosure.",
            },
            {
                "severity": "critical",
                "code": "unsupported_section_conclusion",
                "section_id": "platform_parity",
                "message": "Section contains neither retained evidence nor an explicit unavailable-evidence disclosure.",
            },
            {
                "severity": "warning",
                "code": "thin_section_summary",
                "section_id": "code_audit",
                "message": "Section summary is short.",
            },
        ],
        "progress": [
            {
                "step": "reports",
                "status": "blocked",
                "message": "Mid draft blocked by repeated quality codes.",
                "evidence": {"quality_status": "blocked"},
            }
        ],
        "human_review_required": True,
        "client_ready": False,
    }

    output = apply_mid_quality_issue_display(result)
    labels = output["report_quality_blockers"]
    progress = output["progress"][0]

    assert output["status"] == "blocked"
    assert output["report_generation_status"] == "blocked"
    assert labels == [
        "unsupported_section_conclusion (functional_qa)",
        "unsupported_section_conclusion (platform_parity)",
    ]
    assert "functional_qa" in output["report_generation_error"]
    assert "platform_parity" in output["report_generation_error"]
    assert progress["status"] == "blocked"
    assert progress["evidence"]["critical_issue_labels"] == labels
    assert len(progress["evidence"]["critical_issue_details"]) == 2
    assert output["human_review_required"] is True
    assert output["client_ready"] is False


def test_non_blocked_mid_result_is_not_rewritten() -> None:
    result = {
        "status": "running",
        "report_generation_status": "mid_report_generation_pending",
        "progress": [{"step": "reports", "status": "planned", "message": "Dedicated Mid draft is planned."}],
    }

    output = apply_mid_quality_issue_display(result)

    assert output["status"] == "running"
    assert output["report_generation_status"] == "mid_report_generation_pending"
    assert output["progress"] == result["progress"]
    assert "report_quality_blockers" not in output
