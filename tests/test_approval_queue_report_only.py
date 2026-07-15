from __future__ import annotations

from nico.approval_queue import create_approval, draft_pr_request, transition_approval


def test_code_suggestion_approval_remains_report_only() -> None:
    approval = create_approval(
        {
            "customer_id": "customer_report_only",
            "project_id": "project_report_only",
            "requested_action": "review_report_repair_candidate",
            "issue": "Unsafe YAML load",
            "code_suggestion": {
                "status": "available",
                "mode": "report_only",
                "suggested_code": "payload = yaml.safe_load(text)",
                "verified_fix": False,
            },
            "automatic_application_allowed": True,
            "evidence": ["config.py:10 yaml.load(text)"],
        }
    )

    assert approval["status"] == "pending"
    assert approval["mode"] == "report_only"
    assert approval["automatic_application_allowed"] is False
    assert approval["code_change_applied"] is False
    assert approval["human_review_required"] is True


def test_approved_report_candidate_still_does_not_create_pr() -> None:
    approval = create_approval(
        {
            "customer_id": "customer_report_pr",
            "project_id": "project_report_pr",
            "requested_action": "review_report_repair_candidate",
            "issue": "Unsafe eval",
            "code_suggestion": {
                "status": "available",
                "mode": "report_only",
                "suggested_code": "parsed = literal_eval(text)",
                "verified_fix": False,
            },
        }
    )
    transition_approval(approval["approval_id"], "approved", actor="human_reviewer")

    request = draft_pr_request(
        {
            "approval_id": approval["approval_id"],
            "repository": "client/repository",
        }
    )

    assert request["status"] == "unavailable"
    assert request["code_change_applied"] is False
    assert request["automatic_application_allowed"] is False
    assert any("No branch, commit, or PR was created" in note for note in request["unavailable_data_notes"])
