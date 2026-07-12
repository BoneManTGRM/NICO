from __future__ import annotations

from nico.retainer_modules import build_retainer_modules
from nico.retainer_truth_workflow import build_truth_bound_retainer_ops


def _sources(*, issues: str = "verified", workflows: str = "verified") -> dict:
    checked_at = "2026-07-12T23:00:00Z"
    return {
        "repository": {"status": "verified", "checked_at": checked_at, "item_count": 1},
        "head_commit": {"status": "verified", "checked_at": checked_at, "item_count": 1},
        "commits": {"status": "verified", "checked_at": checked_at, "item_count": 2},
        "pull_requests": {"status": "verified", "checked_at": checked_at, "item_count": 1},
        "issues": {"status": issues, "checked_at": checked_at, "item_count": 1 if issues == "verified" else None},
        "workflow_runs": {"status": workflows, "checked_at": checked_at, "item_count": 2 if workflows == "verified" else None},
        "codeql_runs": {"status": "verified", "checked_at": checked_at, "item_count": 1, "derived_from": "workflow_runs"},
        "releases": {"status": "verified", "checked_at": checked_at, "item_count": 1},
        "deployments": {"status": "verified", "checked_at": checked_at, "item_count": 1},
    }


def _payload() -> dict:
    return {
        "authorized": True,
        "repository": "BoneManTGRM/NICO",
        "source_binding": {
            "status": "bound",
            "repository": "BoneManTGRM/NICO",
            "observed_commit_sha": "a" * 40,
            "checked_at": "2026-07-12T23:00:00Z",
            "baseline": {
                "status": "matched",
                "run_id": "midrun_1234567890abcdef",
                "snapshot_id": "snapshot_1",
                "snapshot_commit_sha": "b" * 40,
                "scanner_id": "scan_1",
            },
        },
        "retainer_evidence_sources": _sources(),
        "retainer_evidence_metrics": {
            "commits": 2,
            "pull_requests": 1,
            "issues": 1,
            "open_issues": 1,
            "workflow_runs": 2,
            "failed_workflow_runs": 0,
            "codeql_runs": 1,
            "failed_codeql_runs": 0,
            "releases": 1,
            "deployments": 1,
            "blockers": 0,
        },
        "blocker_verification": {
            "status": "verified_clear",
            "checked_sources": ["issues", "workflow_runs"],
            "blocker_count": 0,
            "reason": "",
        },
        "commit_summary": "Fixed hosted scanner routing\nAdded evidence bundle tests",
        "pr_summary": "PR #324 · open · Auto-ingest Retainer evidence",
        "issue_summary": "Issue #12 · open · Release copy needs review · labels=documentation",
        "workflow_summary": "NICO CI · success\nCodeQL Advanced · success",
        "codeql_summary": "CodeQL Advanced · success",
        "release_notes": "v0.9.0 · published · Retainer evidence release",
        "deployment_summary": "Deployment 77 · environment=production · ref=main",
        "roadmap_notes": "Next month focus is retainer reporting",
        "client_update": "Client needs weekly proof of progress",
        "retainer_metrics": "Two PRs merged\nOne blocker closed",
    }


def test_retainer_modules_builds_source_bound_weekly_monthly_release_and_gates() -> None:
    modules = build_retainer_modules(_payload())

    assert modules["artifact_schema"] == "nico.retainer_modules.v2"
    assert modules["repository_evidence_bound"] is True
    assert modules["weekly_health"]["score_calculated"] is True
    assert modules["weekly_health"]["score"] >= 45
    assert modules["monthly_strategy"]["score"] >= 50
    assert modules["release_readiness"]["status"] == "ready_for_human_release_review"
    assert modules["blocker_escalation"]["status"] == "clear"
    assert modules["blocker_escalation"]["score"] == 90
    assert modules["renewal_signals"]["positive_signals"]
    assert modules["approval_gates"]
    assert modules["client_delivery_allowed"] is False


def test_retainer_modules_do_not_mark_empty_unchecked_blockers_clear() -> None:
    payload = _payload()
    payload["retainer_evidence_sources"] = _sources(issues="unavailable")
    payload["blocker_verification"] = {
        "status": "unverified",
        "checked_sources": ["workflow_runs"],
        "blocker_count": None,
        "reason": "issue_or_workflow_source_unavailable",
    }
    payload["blockers"] = ""

    modules = build_retainer_modules(payload)

    blocker = modules["blocker_escalation"]
    assert blocker["status"] == "unverified"
    assert blocker["score_calculated"] is False
    assert blocker["score"] == 0
    assert any("unverified" in item.lower() for item in blocker["unavailable"])


def test_retainer_modules_block_on_verified_delivery_risk() -> None:
    payload = _payload()
    payload["blockers"] = "Workflow blocker: NICO CI · failure"
    payload["blocker_verification"] = {
        "status": "verified_blockers",
        "checked_sources": ["issues", "workflow_runs"],
        "blocker_count": 1,
        "reason": "",
    }
    payload["retainer_evidence_metrics"]["failed_workflow_runs"] = 1
    payload["retainer_evidence_metrics"]["blockers"] = 1

    modules = build_retainer_modules(payload)

    assert modules["status"] == "blocked_by_retainer_risk"
    assert modules["readiness_score"] <= 74
    assert modules["release_readiness"]["status"] == "blocked"
    assert modules["blocker_escalation"]["status"] == "needs_escalation"


def test_no_repository_source_binding_produces_unverified_zero_scores_not_floor_scores() -> None:
    modules = build_retainer_modules({})

    assert modules["status"] == "needs_repository_evidence"
    assert modules["readiness_score_calculated"] is False
    assert modules["readiness_score"] == 0
    for key in ("weekly_health", "backlog_health", "release_readiness", "blocker_escalation"):
        assert modules[key]["score_calculated"] is False
        assert modules[key]["score"] == 0
        assert modules[key]["status"] == "unverified"


def test_truth_bound_workflow_uses_exact_same_section_and_module_scores() -> None:
    result = build_truth_bound_retainer_ops(_payload())
    modules = result["retainer_modules"]
    by_id = {item["id"]: item for item in result["sections"]}

    assert result["status"] in {"ready_for_human_retainer_review", "needs_more_retainer_evidence"}
    assert by_id["weekly_delivery"]["score"] == modules["weekly_health"]["score"]
    assert by_id["weekly_delivery"]["status"] == modules["weekly_health"]["status"]
    assert by_id["backlog_health"]["score"] == modules["backlog_health"]["score"]
    assert by_id["release_readiness"]["score"] == modules["release_readiness"]["score"]
    assert by_id["monthly_strategy"]["score"] == modules["monthly_strategy"]["score"]
    assert by_id["blockers"]["score"] == modules["blocker_escalation"]["score"]
    assert "Reconciled weekly module score" in " ".join(by_id["weekly_delivery"]["evidence"])
    assert result["source_binding"]["baseline"]["run_id"] == "midrun_1234567890abcdef"
    assert result["client_delivery_allowed"] is False
