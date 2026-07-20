from __future__ import annotations

from nico.workflow_preflight import build_workflow_preflight, build_workflow_preflight_batch


def _comprehensive_payload(**overrides):
    payload = {
        "workflow": "comprehensive",
        "repository": "owner/repo",
        "authorized": True,
        "authorized_by": "reviewer",
        "authorization_scope": "repository assessment only",
        "qa_evidence": "PASS iOS login works",
        "parity_notes": "iOS and Android labels match",
        "stakeholder_notes": "Goal is launch faster",
        "roadmap_notes": "Month 1 QA stabilization",
        "known_risks": "No known launch blocker",
    }
    payload.update(overrides)
    return payload


def test_workflow_preflight_requires_authorization_for_express():
    preflight = build_workflow_preflight(
        {
            "workflow": "express",
            "repository": "owner/repo",
            "authorized": False,
            "scanner_worker_artifact": {"status": "complete"},
        }
    )

    assert preflight["artifact_schema"] == "nico.workflow_preflight.v2"
    assert preflight["status"] == "blocked_preflight"
    assert preflight["allowed_to_run"] is False
    assert preflight["recommended_workflow"] == "express"
    assert preflight["target_endpoint"] == "POST /assessment/express-run"
    assert preflight["blockers"]
    assert any(item["field"] == "authorized" and not item["present"] for item in preflight["field_status"])


def test_workflow_preflight_builds_ready_comprehensive_request_template():
    preflight = build_workflow_preflight(_comprehensive_payload())

    assert preflight["status"] == "ready_to_submit"
    assert preflight["allowed_to_run"] is True
    assert preflight["recommended_workflow"] == "comprehensive"
    assert preflight["target_endpoint"] == "POST /assessment/mid-run"
    assert preflight["missing_fields"] == []
    assert preflight["request_template"]["payload"]["qa_evidence"] == "PASS iOS login works"
    assert preflight["request_template"]["payload"]["service_tier"] == "comprehensive"
    assert preflight["next_action"] == "Submit the request template."


def test_legacy_full_alias_resolves_to_comprehensive_internal_profile():
    preflight = build_workflow_preflight(_comprehensive_payload(workflow="full"))

    assert preflight["recommended_workflow"] == "comprehensive"
    assert preflight["internal_execution_profile"] == "full"
    assert preflight["target_endpoint"] == "POST /assessment/mid-run"


def test_monitor_execute_requires_authorization_and_missing_evidence_is_explicit():
    preflight = build_workflow_preflight(
        {
            "workflow": "monitor_execute",
            "authorized": False,
            "commit_summary": "Fixed report export path",
            "pr_summary": "Opened operations PR",
        }
    )

    assert preflight["status"] == "blocked_preflight"
    assert preflight["allowed_to_run"] is False
    assert preflight["recommended_workflow"] == "monitor_execute"
    assert "issue_summary" in preflight["missing_fields"]
    assert preflight["request_template"]["endpoint"] == "POST /retainer/ops"


def test_workflow_preflight_batch_counts_ready_and_blocked():
    batch = build_workflow_preflight_batch(
        [
            _comprehensive_payload(),
            {
                "workflow": "express",
                "repository": "owner/repo",
                "authorized": False,
            },
        ]
    )

    assert batch["artifact_schema"] == "nico.workflow_preflight_batch.v2"
    assert batch["count"] == 2
    assert batch["ready_count"] == 1
    assert batch["blocked_count"] == 1
