from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_durable_duplicate_start_guard.v1"
_PATCH_MARKER = "_nico_express_durable_duplicate_start_guard_v1"
_ACTIVE_STATUSES = {"queued", "running", "starting", "pending", "temporarily_unavailable"}
_FRESH_SECONDS = 1200


def _record_response(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("response") if isinstance(record.get("response"), dict) else record.get("payload")
    return deepcopy(value) if isinstance(value, dict) else {}


def _parse_time(value: Any) -> datetime | None:
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


def _age_seconds(value: Any) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _scope(record: dict[str, Any]) -> tuple[str, str, str]:
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    response = _record_response(record)
    return (
        str(record.get("repository") or request.get("repository") or response.get("repository") or ""),
        str(record.get("customer_id") or request.get("customer_id") or response.get("customer_id") or "default_customer"),
        str(record.get("project_id") or request.get("project_id") or response.get("project_id") or "default_project"),
    )


def find_fresh_durable_run(store: Any, scope: tuple[str, str, str]) -> dict[str, Any] | None:
    try:
        records = store.list("assessment_runs", customer_id=scope[1], project_id=scope[2])
    except Exception:
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for record in records:
        if not isinstance(record, dict) or str(record.get("workflow") or "") != "express":
            continue
        if _scope(record) != scope:
            continue
        response = _record_response(record)
        status = str(response.get("status") or record.get("status") or "").lower()
        if status not in _ACTIVE_STATUSES:
            continue
        scanner = response.get("scanner") if isinstance(response.get("scanner"), dict) else {}
        timestamp = (
            scanner.get("heartbeat_at")
            or response.get("heartbeat_at")
            or response.get("updated_at")
            or record.get("updated_at")
            or record.get("created_at")
        )
        age = _age_seconds(timestamp)
        if age is None or age > _FRESH_SECONDS:
            continue
        candidates.append((age, response))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    output = deepcopy(candidates[0][1])
    output["duplicate_start_prevented"] = True
    output["duplicate_start_guard"] = {
        "version": PATCH_VERSION,
        "source": "durable_assessment_run_scan",
        "freshness_seconds": _FRESH_SECONDS,
        "cross_worker": True,
    }
    output.setdefault("human_review_required", True)
    output["client_ready"] = False
    return output


def install_express_durable_duplicate_start_guard() -> dict[str, Any]:
    from nico import express_async_api as api
    from nico import hosted_assessment as hosted

    current: Callable[[Any], dict[str, Any]] = api.express_assessment_start
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def guarded_start(req: Any) -> dict[str, Any]:
        payload = api._model_payload(req)
        if bool(payload.get("authorized")) and bool(payload.get("authorization_confirmed")):
            try:
                repository = hosted.normalize_repository(str(payload.get("repository") or ""))
            except ValueError:
                repository = ""
            if repository:
                scope = (
                    repository,
                    str(payload.get("customer_id") or "default_customer"),
                    str(payload.get("project_id") or "default_project"),
                )
                existing = find_fresh_durable_run(api.STORE, scope)
                if existing is not None:
                    return existing
        return current(req)

    setattr(guarded_start, _PATCH_MARKER, True)
    setattr(guarded_start, "_nico_previous", current)
    api.express_assessment_start = guarded_start
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "durable_scope_scan": True,
        "cross_worker_duplicate_start_prevented": True,
        "freshness_seconds": _FRESH_SECONDS,
        "stale_records_block_new_runs": False,
    }


__all__ = [
    "PATCH_VERSION",
    "find_fresh_durable_run",
    "install_express_durable_duplicate_start_guard",
]
