from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

VERSION = "cross_tier_run_recovery_v1"
TIERS = ("express", "mid", "full")
TERMINAL = {"completed", "failed", "cancelled", "expired"}
ACTIVE = {"queued", "running", "recovering"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def reconcile_run_status(
    preserved: Mapping[str, Any],
    *,
    live_status: Mapping[str, Any] | None,
    persisted_candidates: Iterable[Mapping[str, Any]] = (),
    now: datetime | None = None,
    missing_timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Recover one Express, Mid, or Full run without creating duplicates."""
    record = _mapping(preserved)
    issues: list[str] = []
    tier = str(record.get("tier") or "").lower()
    if tier not in TIERS:
        issues.append("invalid_tier")

    identity = {
        "assessment_id": str(record.get("assessment_id") or ""),
        "workspace_id": str(record.get("workspace_id") or ""),
        "repository_id": str(record.get("repository_id") or ""),
        "snapshot_sha": str(record.get("snapshot_sha") or ""),
        "tier": tier,
    }
    for key, value in identity.items():
        if not value:
            issues.append(f"missing_{key}")

    live = _mapping(live_status)
    if live and int(live.get("http_status") or 200) != 404:
        status = str(live.get("status") or "running").lower()
        return {
            "version": VERSION,
            "status": status,
            "source": "live",
            "issues": issues,
            "run_id": str(live.get("run_id") or record.get("run_id") or ""),
            "recovered": False,
            "replacement_allowed": status in TERMINAL,
            "duplicate_start_blocked": status in ACTIVE,
            "record": live,
        }

    matches: list[dict[str, Any]] = []
    for candidate_value in persisted_candidates:
        candidate = _mapping(candidate_value)
        if all(str(candidate.get(key) or "").lower() == value.lower() for key, value in identity.items()):
            matches.append(candidate)

    if len(matches) > 1:
        matches.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        issues.append("multiple_persisted_matches")
    if matches:
        recovered = matches[0]
        status = str(recovered.get("status") or "recovering").lower()
        return {
            "version": VERSION,
            "status": status,
            "source": "persisted",
            "issues": issues,
            "run_id": str(recovered.get("run_id") or record.get("run_id") or ""),
            "recovered": True,
            "replacement_allowed": status in TERMINAL,
            "duplicate_start_blocked": status in ACTIVE,
            "record": recovered,
        }

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    last_seen = _iso(record.get("last_seen_at") or record.get("updated_at") or record.get("started_at"))
    age = (current - last_seen).total_seconds() if last_seen else None
    timed_out = age is None or age >= max(1, int(missing_timeout_seconds))
    status = "expired" if timed_out else "recovering"
    issues.append("run_not_found")
    if timed_out:
        issues.append("missing_run_timeout_exceeded")
    return {
        "version": VERSION,
        "status": status,
        "source": "missing",
        "issues": issues,
        "run_id": str(record.get("run_id") or ""),
        "recovered": False,
        "replacement_allowed": timed_out,
        "duplicate_start_blocked": not timed_out,
        "retry_status_lookup_allowed": not timed_out,
        "record": record,
    }


__all__ = ["ACTIVE", "TERMINAL", "TIERS", "VERSION", "reconcile_run_status"]
