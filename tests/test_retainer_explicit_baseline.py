from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nico.retainer_evidence_ingestion_v2 import build_retainer_evidence_payload_v2
from nico.retainer_truth_workflow import build_truth_bound_retainer_ops


class _Client:
    def repo_url(self, repo: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repo}{path}"

    def get_repo(self, repo: str):
        return {"full_name": repo, "default_branch": "main", "visibility": "public"}, None

    def get_commits(self, repo: str, since_iso: str):
        return [], None

    def get_pulls(self, repo: str, since: datetime):
        return [], None

    def get_workflow_runs(self, repo: str, since_iso: str):
        return [], None

    def get_json(self, url: str, params: dict[str, Any] | None = None):
        if url.endswith("/commits/main"):
            return {"sha": "a" * 40}, None
        if url.endswith("/issues") or url.endswith("/releases") or url.endswith("/deployments"):
            return [], None
        raise AssertionError((url, params))


class _Store:
    def get(self, table: str, item_id: str):
        return None

    def list(self, table: str, customer_id=None, project_id=None):
        return []


def test_requested_missing_baseline_does_not_fall_back_to_repository_only_evidence() -> None:
    result = build_retainer_evidence_payload_v2(
        {
            "repository": "BoneManTGRM/NICO",
            "authorized": True,
            "customer_id": "customer_1",
            "project_id": "project_1",
            "baseline_run_id": "midrun_missing123456",
            "timeframe_days": 30,
            "roadmap_notes": "Approved roadmap context",
        },
        store=_Store(),
        client=_Client(),
        now=datetime(2026, 7, 12, 23, 30, 0, tzinfo=timezone.utc),
    )

    assert result["source_binding"]["status"] == "baseline_mismatch"
    assert result["source_binding"]["baseline"]["requested_run_id"] == "midrun_missing123456"
    assert result["technical_evidence_auto_ingested"] is False
    assert result["retainer_evidence_sources"] == {}
    assert result["blocker_verification"]["status"] == "unverified"
    assert result["retainer_evidence_ingestion"]["code"] == "explicit_baseline_not_matched"
    for field in (
        "commit_summary",
        "pr_summary",
        "issue_summary",
        "workflow_summary",
        "codeql_summary",
        "release_notes",
        "deployment_summary",
        "blockers",
    ):
        assert result[field] == ""

    workflow = build_truth_bound_retainer_ops(result)
    assert workflow["retainer_modules"]["repository_evidence_bound"] is False
    assert workflow["maturity_signal"]["calculated"] is False
    assert workflow["maturity_signal"]["score"] == 0
    assert workflow["evidence_readiness"]["calculated"] is False
    assert workflow["evidence_readiness"]["readiness_score"] == 0
    assert all(item["score_calculated"] is False for item in workflow["sections"])
    assert all(item["score"] == 0 for item in workflow["sections"])
