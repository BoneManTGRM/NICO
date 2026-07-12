from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from nico.retainer_evidence_ingestion import build_retainer_evidence_payload


NOW = datetime(2026, 7, 12, 23, 10, 0, tzinfo=timezone.utc)


class _Client:
    def __init__(self, *, fail_issues: bool = False, failed_workflow: bool = False) -> None:
        self.fail_issues = fail_issues
        self.failed_workflow = failed_workflow

    def repo_url(self, repo: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repo}{path}"

    def get_repo(self, repo: str):
        return {
            "full_name": repo,
            "default_branch": "main",
            "visibility": "public",
        }, None

    def get_commits(self, repo: str, since_iso: str):
        return [
            {
                "sha": "a" * 40,
                "commit": {
                    "message": "Repair Retainer evidence path",
                    "author": {"name": "NICO", "date": "2026-07-12T22:00:00Z"},
                },
                "author": {"login": "BoneManTGRM"},
            }
        ], None

    def get_pulls(self, repo: str, since: datetime):
        return [
            {
                "number": 324,
                "title": "Auto-ingest Retainer evidence",
                "state": "open",
                "merged_at": None,
                "updated_at": "2026-07-12T22:30:00Z",
            }
        ], None

    def get_workflow_runs(self, repo: str, since_iso: str):
        conclusion = "failure" if self.failed_workflow else "success"
        return [
            {
                "name": "NICO CI",
                "display_title": "NICO CI",
                "conclusion": conclusion,
                "status": "completed",
                "event": "pull_request",
                "created_at": "2026-07-12T22:35:00Z",
                "head_sha": "a" * 40,
            },
            {
                "name": "CodeQL Advanced",
                "display_title": "CodeQL Advanced",
                "conclusion": "success",
                "status": "completed",
                "event": "pull_request",
                "created_at": "2026-07-12T22:36:00Z",
                "head_sha": "a" * 40,
            },
        ], None

    def get_json(self, url: str, params: dict[str, Any] | None = None):
        if url.endswith("/commits/main"):
            return {"sha": "a" * 40}, None
        if url.endswith("/issues"):
            if self.fail_issues:
                return None, "GitHub returned 403: secret provider body must not leak"
            return [
                {
                    "number": 12,
                    "title": "Document release procedure",
                    "state": "open",
                    "updated_at": "2026-07-12T22:20:00Z",
                    "labels": [{"name": "documentation"}],
                }
            ], None
        if url.endswith("/releases"):
            return [
                {
                    "tag_name": "v0.9.0",
                    "name": "Retainer evidence release",
                    "draft": False,
                    "prerelease": False,
                    "published_at": "2026-07-12T21:00:00Z",
                }
            ], None
        if url.endswith("/deployments"):
            return [
                {
                    "id": 77,
                    "environment": "production",
                    "ref": "main",
                    "sha": "a" * 40,
                    "created_at": "2026-07-12T21:30:00Z",
                }
            ], None
        raise AssertionError(url)


def _payload() -> dict[str, Any]:
    return {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "customer_id": "customer_1",
        "project_id": "project_1",
        "timeframe_days": 30,
        "roadmap_notes": "Complete truth-bound Retainer evidence",
    }


def _mid_baseline() -> dict[str, Any]:
    return {
        "status": "complete",
        "run_id": "midrun_1234567890abcdef",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "repository_snapshot": {
            "snapshot_id": "snapshot_1",
            "commit_sha": "b" * 40,
        },
        "scanner": {"scan_id": "scan_1", "status": "complete"},
        "generated_at": "2026-07-12T20:00:00Z",
    }


def test_auto_ingestion_binds_repository_baseline_and_all_verified_sources() -> None:
    result = build_retainer_evidence_payload(
        _payload(),
        latest_mid=_mid_baseline(),
        client=_Client(),
        now=NOW,
    )

    assert result["source_binding"]["status"] == "bound"
    assert result["source_binding"]["observed_commit_sha"] == "a" * 40
    assert result["source_binding"]["baseline"]["run_id"] == "midrun_1234567890abcdef"
    assert result["source_binding"]["baseline"]["snapshot_id"] == "snapshot_1"
    assert result["source_binding"]["baseline"]["scanner_id"] == "scan_1"
    assert result["technical_evidence_auto_ingested"] is True
    assert "Repair Retainer evidence path" in result["commit_summary"]
    assert "PR #324" in result["pr_summary"]
    assert "Issue #12" in result["issue_summary"]
    assert "CodeQL Advanced" in result["codeql_summary"]
    assert "v0.9.0" in result["release_notes"]
    assert "Deployment 77" in result["deployment_summary"]
    assert result["blocker_verification"]["status"] == "verified_clear"
    assert result["retainer_evidence_metrics"]["failed_workflow_runs"] == 0
    assert result["retainer_evidence_ingestion"]["client_delivery_allowed"] is False


def test_partial_source_failure_stays_unverified_and_scrubs_provider_body() -> None:
    result = build_retainer_evidence_payload(
        _payload(),
        latest_mid=_mid_baseline(),
        client=_Client(fail_issues=True),
        now=NOW,
    )
    rendered = repr(result)

    assert result["retainer_evidence_sources"]["issues"]["status"] == "unavailable"
    assert result["retainer_evidence_sources"]["issues"]["note"] == "GitHub source returned HTTP 403."
    assert result["blocker_verification"]["status"] == "unverified"
    assert result["blocker_verification"]["blocker_count"] is None
    assert "secret provider body" not in rendered


def test_failed_workflow_is_a_verified_blocker() -> None:
    result = build_retainer_evidence_payload(
        _payload(),
        latest_mid=_mid_baseline(),
        client=_Client(failed_workflow=True),
        now=NOW,
    )

    assert result["blocker_verification"]["status"] == "verified_blockers"
    assert result["blocker_verification"]["blocker_count"] == 1
    assert "Workflow blocker" in result["blockers"]
    assert result["retainer_evidence_metrics"]["failed_workflow_runs"] == 1


def test_no_repository_or_baseline_returns_unbound_without_placeholder_evidence() -> None:
    result = build_retainer_evidence_payload(
        {
            "authorized": True,
            "customer_id": "customer_1",
            "project_id": "project_1",
        },
        client=_Client(),
        now=NOW,
    )

    assert result["source_binding"]["status"] == "unbound"
    assert result["technical_evidence_auto_ingested"] is False
    assert result["retainer_evidence_sources"] == {}
    assert result["blocker_verification"]["status"] == "unverified"
    for key in ("commit_summary", "pr_summary", "issue_summary", "release_notes"):
        assert not result.get(key)


def test_mismatched_baseline_is_not_reused_for_a_different_project_scope() -> None:
    baseline = deepcopy(_mid_baseline())
    baseline["project_id"] = "other_project"

    result = build_retainer_evidence_payload(
        _payload(),
        latest_mid=baseline,
        client=_Client(),
        now=NOW,
    )

    assert result["source_binding"]["baseline"]["status"] == "repository_only"
    assert result["source_binding"]["baseline"]["run_id"] == ""
    assert result["source_binding"]["baseline"]["snapshot_id"] == ""
