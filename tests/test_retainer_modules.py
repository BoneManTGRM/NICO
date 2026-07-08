from __future__ import annotations

from nico.retainer_modules import build_retainer_modules
from nico.service_workflows import build_retainer_ops


def test_retainer_modules_builds_weekly_monthly_release_and_gates():
    modules = build_retainer_modules(
        {
            "commit_summary": "Fixed hosted scanner routing\nAdded evidence bundle tests",
            "pr_summary": "Merged PR 108 client acceptance workflow",
            "issue_summary": "Open issue: release copy needs review",
            "release_notes": "Release candidate includes acceptance gate and evidence bundle",
            "roadmap_notes": "Next month focus is retainer reporting",
            "client_update": "Client needs weekly proof of progress",
            "retainer_metrics": "Two PRs merged\nOne blocker closed",
        }
    )

    assert modules["artifact_schema"] == "nico.retainer_modules.v1"
    assert modules["status"] == "needs_more_retainer_evidence"
    assert modules["weekly_health"]["score"] >= 50
    assert modules["monthly_strategy"]["score"] >= 50
    assert modules["release_readiness"]["status"] == "ready_for_human_release_review"
    assert modules["blocker_escalation"]["status"] == "clear"
    assert modules["renewal_signals"]["positive_signals"]
    assert modules["approval_gates"]


def test_retainer_modules_blocks_on_delivery_risk():
    modules = build_retainer_modules(
        {
            "blockers": "Critical blocker: production deploy failed",
            "release_notes": "Release candidate prepared",
        }
    )

    assert modules["status"] == "blocked_by_retainer_risk"
    assert modules["readiness_score"] <= 74
    assert modules["release_readiness"]["status"] == "blocked"
    assert modules["blocker_escalation"]["status"] == "needs_escalation"


def test_retainer_ops_attaches_structured_retainer_modules():
    result = build_retainer_ops(
        {
            "authorized": True,
            "commit_summary": "Fixed report export path",
            "pr_summary": "Opened retainer module PR",
            "issue_summary": "Client wants weekly status",
            "release_notes": "Release candidate includes rollback notes",
            "roadmap_notes": "Next month focus is customer dashboard",
            "client_update": "Weekly client summary sent",
            "retainer_metrics": "One release candidate prepared",
        }
    )

    assert result["status"] == "complete"
    assert result["retainer_modules"]["artifact_schema"] == "nico.retainer_modules.v1"
    assert result["weekly_status_report"]
    assert result["monthly_strategy_report"]
    assert result["release_checklist"]
    assert any("Retainer weekly health status" in item for item in result["sections"][0]["evidence"])
