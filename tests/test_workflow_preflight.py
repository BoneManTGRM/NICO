from __future__ import annotations

from nico.workflow_preflight import build_workflow_preflight, build_workflow_preflight_batch


def test_workflow_preflight_requires_authorization_for_express():
    preflight = build_workflow_preflight(
        {
            "workflow": "express",
            "repository": "owner/repo",
            "authorized": False,
            "scanner_worker_artifact": {"status": "complete"},
        }
    )

    assert preflight["artifact_schema"] == "nico.workflow_preflight.v1"
    assert preflight["status"] == "blocked_preflight"
    assert preflight["allowed_to_run"] is False
    assert preflight["recommended_workflow"] == "express"
    assert preflight["target_endpoint"] == "POST /assessment/github"
    assert preflight["blockers"]
    assert any(item["field"] == "authorized" and not item["present"] for item in preflight["field_status"])


def test_workflow_preflight_builds_ready_mid_request_template():
    preflight = build_workflow_preflight(
        {
            "workflow": "mid",
            "authorized": True,
            "qa_evidence": "PASS iOS login works",
            "parity_notes": "iOS and Android labels match",
            "stakeholder_notes": "Goal is launch faster",
            "roadmap_notes": "Month 1 QA stabilization",
            "known_risks": "No known launch blocker",
        }
    )

    assert preflight["status"] == "ready_to_submit"
    assert preflight["allowed_to_run"] is True
    assert preflight["target_endpoint"] == "POST /assessment/mid"
    assert preflight["missing_fields"] == []
    assert preflight["request_template"]["payload"]["qa_evidence"] == "PASS iOS login works"
    assert preflight["next_action"] == "Submit the request template."


def test_workflow_preflight_marks_retainer_missing_evidence():
    preflight = build_workflow_preflight(
        {
            "workflow": "retainer",
            "commit_summary": "Fixed report export path",
            "pr_summary": "Opened retainer PR",
        }
    )

    assert preflight["status"] == "needs_more_preflight_evidence"
    assert preflight["allowed_to_run"] is False
    assert preflight["recommended_workflow"] == "retainer"
    assert "issue_summary" in preflight["missing_fields"]
    assert preflight["request_template"]["endpoint"] == "POST /retainer/ops"


def test_workflow_preflight_batch_counts_ready_and_blocked():
    batch = build_workflow_preflight_batch(
        [
            {
                "workflow": "mid",
                "authorized": True,
                "qa_evidence": "PASS login",
                "parity_notes": "same labels",
                "stakeholder_notes": "goal launch",
                "roadmap_notes": "month 1",
                "known_risks": "none",
            },
            {
                "workflow": "express",
                "repository": "owner/repo",
                "authorized": False,
            },
        ]
    )

    assert batch["artifact_schema"] == "nico.workflow_preflight_batch.v1"
    assert batch["count"] == 2
    assert batch["ready_count"] == 1
    assert batch["blocked_count"] == 1
