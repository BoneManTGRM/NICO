from datetime import datetime, timedelta, timezone

from nico.cross_tier_run_recovery_v1 import reconcile_run_status


def _preserved(tier: str = "express") -> dict:
    return {
        "run_id": f"{tier}_run_1",
        "assessment_id": "assessment-1",
        "workspace_id": "workspace-1",
        "repository_id": "repo-1",
        "snapshot_sha": "a" * 40,
        "tier": tier,
        "last_seen_at": "2026-07-18T00:00:00Z",
    }


def test_live_run_remains_active_and_blocks_duplicate_start() -> None:
    result = reconcile_run_status(
        _preserved("express"),
        live_status={"http_status": 200, "run_id": "express_run_1", "status": "running"},
    )
    assert result["source"] == "live"
    assert result["duplicate_start_blocked"] is True
    assert result["replacement_allowed"] is False


def test_404_recovers_matching_persisted_run_for_each_tier() -> None:
    for tier in ("express", "mid", "full"):
        preserved = _preserved(tier)
        persisted = {**preserved, "status": "running", "updated_at": "2026-07-18T00:02:00Z"}
        result = reconcile_run_status(
            preserved,
            live_status={"http_status": 404},
            persisted_candidates=[persisted],
        )
        assert result["source"] == "persisted"
        assert result["recovered"] is True
        assert result["duplicate_start_blocked"] is True


def test_recent_missing_run_stays_recovering_without_duplicate() -> None:
    result = reconcile_run_status(
        _preserved(),
        live_status={"http_status": 404},
        now=datetime(2026, 7, 18, 0, 2, tzinfo=timezone.utc),
        missing_timeout_seconds=300,
    )
    assert result["status"] == "recovering"
    assert result["retry_status_lookup_allowed"] is True
    assert result["replacement_allowed"] is False
    assert result["duplicate_start_blocked"] is True


def test_missing_run_expires_after_bounded_timeout_and_allows_replacement() -> None:
    result = reconcile_run_status(
        _preserved("full"),
        live_status={"http_status": 404},
        now=datetime(2026, 7, 18, 0, 10, tzinfo=timezone.utc),
        missing_timeout_seconds=300,
    )
    assert result["status"] == "expired"
    assert "missing_run_timeout_exceeded" in result["issues"]
    assert result["replacement_allowed"] is True
    assert result["duplicate_start_blocked"] is False


def test_cross_tier_candidate_is_never_used_for_recovery() -> None:
    preserved = _preserved("mid")
    wrong = {**preserved, "tier": "express", "status": "running"}
    result = reconcile_run_status(
        preserved,
        live_status={"http_status": 404},
        persisted_candidates=[wrong],
        now=datetime(2026, 7, 18, 0, 10, tzinfo=timezone.utc),
    )
    assert result["source"] == "missing"
    assert result["recovered"] is False


def test_identity_gaps_fail_closed() -> None:
    preserved = _preserved()
    preserved["snapshot_sha"] = ""
    result = reconcile_run_status(
        preserved,
        live_status={"http_status": 404},
        now=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert "missing_snapshot_sha" in result["issues"]
    assert result["recovered"] is False
