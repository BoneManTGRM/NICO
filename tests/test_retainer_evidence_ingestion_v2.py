from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nico.retainer_evidence_ingestion_v2 import build_retainer_evidence_payload_v2

NOW = datetime(2026, 7, 12, 23, 20, 0, tzinfo=timezone.utc)


class _Client:
    def __init__(
        self,
        *,
        open_issue_blocker: bool = False,
        fail_open_issues: bool = False,
        newer_success: bool = False,
    ) -> None:
        self.open_issue_blocker = open_issue_blocker
        self.fail_open_issues = fail_open_issues
        self.newer_success = newer_success

    def repo_url(self, repo: str, path: str = "") -> str:
        return f"https://api.github.test/repos/{repo}{path}"

    def get_repo(self, repo: str):
        return {"full_name": repo, "default_branch": "main", "visibility": "public"}, None

    def get_commits(self, repo: str, since_iso: str):
        return [], None

    def get_pulls(self, repo: str, since: datetime):
        return [], None

    def get_workflow_runs(self, repo: str, since_iso: str):
        rows = [
            {
                "name": "NICO CI",
                "display_title": "NICO CI",
                "conclusion": "failure",
                "status": "completed",
                "event": "pull_request",
                "created_at": "2026-07-11T20:00:00Z",
                "head_sha": "a" * 40,
            },
            {
                "name": "CodeQL Advanced",
                "display_title": "CodeQL Advanced",
                "conclusion": "success",
                "status": "completed",
                "event": "pull_request",
                "created_at": "2026-07-12T20:00:00Z",
                "head_sha": "b" * 40,
            },
        ]
        if self.newer_success:
            rows.append(
                {
                    "name": "NICO CI",
                    "display_title": "NICO CI",
                    "conclusion": "success",
                    "status": "completed",
                    "event": "pull_request",
                    "created_at": "2026-07-12T22:00:00Z",
                    "head_sha": "c" * 40,
                }
            )
        return rows, None

    def get_json(self, url: str, params: dict[str, Any] | None = None):
        if url.endswith("/commits/main"):
            return {"sha": "c" * 40}, None
        if url.endswith("/issues"):
            state = str((params or {}).get("state") or "")
            if state == "open":
                if self.fail_open_issues:
                    return None, "GitHub returned 403: private body"
                if self.open_issue_blocker:
                    return [
                        {
                            "number": 91,
                            "title": "Production release blocked",
                            "state": "open",
                            "updated_at": "2026-06-01T10:00:00Z",
                            "labels": [{"name": "blocker"}],
                        }
                    ], None
                return [], None
            return [], None
        if url.endswith("/releases") or url.endswith("/deployments"):
            return [], None
        raise AssertionError((url, params))


def _payload() -> dict[str, Any]:
    return {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "customer_id": "customer_1",
        "project_id": "project_1",
        "timeframe_days": 30,
    }


def test_old_failed_workflow_does_not_remain_a_blocker_after_newer_success() -> None:
    result = build_retainer_evidence_payload_v2(
        _payload(),
        client=_Client(newer_success=True),
        now=NOW,
    )

    assert result["blocker_verification"]["status"] == "verified_clear"
    assert result["blocker_verification"]["blocker_count"] == 0
    assert result["retainer_evidence_metrics"]["failed_workflow_runs"] == 0
    assert result["blockers"] == ""
    assert result["retainer_evidence_sources"]["latest_workflow_state"]["status"] == "verified"


def test_current_open_blocker_is_detected_without_timeframe_cutoff() -> None:
    result = build_retainer_evidence_payload_v2(
        _payload(),
        client=_Client(open_issue_blocker=True, newer_success=True),
        now=NOW,
    )

    assert result["blocker_verification"]["status"] == "verified_blockers"
    assert result["blocker_verification"]["blocker_count"] == 1
    assert "Issue #91" in result["blockers"]
    assert result["retainer_evidence_metrics"]["open_issues"] == 1
    assert result["retainer_evidence_ingestion"]["artifact_schema"] == "nico.retainer_evidence_ingestion.v2"
    assert "without a timeframe cutoff" in result["retainer_evidence_sources"]["open_issues"]["note"]


def test_open_issue_source_failure_prevents_verified_clear_status() -> None:
    result = build_retainer_evidence_payload_v2(
        _payload(),
        client=_Client(fail_open_issues=True, newer_success=True),
        now=NOW,
    )
    rendered = repr(result)

    assert result["retainer_evidence_sources"]["open_issues"]["status"] == "unavailable"
    assert result["blocker_verification"]["status"] == "unverified"
    assert result["blocker_verification"]["blocker_count"] is None
    assert "private body" not in rendered
    assert result["retainer_evidence_metrics"]["open_issues"] is None
