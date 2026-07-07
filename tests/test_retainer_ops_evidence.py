from nico.retainer_ops_evidence import build_retainer_ops_evidence


def test_retainer_ops_evidence_flags_missing_operating_inputs():
    result = build_retainer_ops_evidence({})

    assert result["target"] == 70
    assert "roadmap_backlog" in result["missing"]
    assert "weekly_status" in result["missing"]
    assert result["next_actions"]


def test_retainer_ops_evidence_reaches_target_with_full_operating_inputs():
    result = build_retainer_ops_evidence(
        {
            "roadmap_notes": "Milestone A\nMilestone B",
            "sprint_cadence": {"length": "2 weeks"},
            "release_notes": "Release candidate ready",
            "issues": "Payment bug owner: team\nLogin UX owner: team",
            "review_queue": ["Release go/no-go"],
            "weekly_status_report": ["Completed setup", "Next action release review"],
            "quality_traceability": {"requirements": "tickets and QA notes linked"},
            "client_update": "Draft client summary prepared for human review",
        }
    )

    assert result["score"] == 70
    assert result["missing"] == []
    assert result["status"] == "green"
