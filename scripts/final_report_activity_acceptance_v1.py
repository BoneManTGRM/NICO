from __future__ import annotations

from typing import Any, Mapping

VERSION = "nico.final_report_activity_acceptance.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _bounded_activity(payload: Mapping[str, Any]) -> dict[str, Any]:
    activity = _mapping(payload.get("active_stage_execution"))
    return {
        "artifact_schema": str(activity.get("artifact_schema") or ""),
        "stage_id": str(activity.get("stage_id") or ""),
        "status": str(activity.get("status") or ""),
        "phase": str(activity.get("phase") or ""),
        "lease_fingerprint": str(activity.get("lease_fingerprint") or ""),
        "durable_job_status": str(activity.get("durable_job_status") or ""),
        "heartbeat_epoch": _number(activity.get("heartbeat_epoch")),
        "heartbeat_age_seconds": _number(activity.get("heartbeat_age_seconds")),
        "heartbeat_fresh": activity.get("heartbeat_fresh") is True,
        "activity_token": str(activity.get("activity_token") or ""),
        "local_worker_active": activity.get("local_worker_active") is True,
        "orphan_after_seconds": _number(activity.get("orphan_after_seconds")),
        "canonical_run_revision_mutated": (
            activity.get("canonical_run_revision_mutated") is True
        ),
        "human_review_required": activity.get("human_review_required") is True,
        "client_delivery_allowed": activity.get("client_delivery_allowed") is True,
    }


def install(runtime: Any) -> dict[str, Any]:
    """Count advancing durable heartbeats as activity without faking run progress.

    Canonical progress and revision intentionally remain stable while a report is
    queued or rendering. The product now exposes a separate bounded heartbeat token.
    The normal 15-minute no-progress ceiling remains in force when that token stops
    advancing, and the existing hard overall ceiling remains unchanged.
    """

    if getattr(runtime, "_nico_final_report_activity_acceptance_installed", False):
        return {"status": "already_installed", "version": VERSION}

    original_summary = runtime._status_summary
    original_signature = runtime._activity_signature

    def status_summary(
        payload: dict[str, Any],
        *,
        http_status: int | None = None,
    ) -> dict[str, Any]:
        summary = original_summary(payload, http_status=http_status)
        summary["active_stage_execution"] = _bounded_activity(payload)
        return summary

    def activity_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
        base = tuple(original_signature(payload))
        activity = _bounded_activity(payload)
        fresh_token = (
            activity["activity_token"]
            if activity["heartbeat_fresh"] is True
            else ""
        )
        return (
            *base,
            activity["stage_id"],
            activity["phase"],
            activity["durable_job_status"],
            fresh_token,
            activity["heartbeat_fresh"],
        )

    runtime._status_summary = status_summary
    runtime._activity_signature = activity_signature
    runtime._nico_final_report_activity_acceptance_installed = True
    return {
        "status": "installed",
        "version": VERSION,
        "fresh_heartbeat_counts_as_observable_activity": True,
        "canonical_progress_fabricated": False,
        "canonical_revision_mutated": False,
        "stale_heartbeat_still_fails": True,
        "hard_acceptance_ceiling_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install"]
