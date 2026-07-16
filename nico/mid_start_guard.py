from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from nico.storage import STORE

MID_START_GUARD_VERSION = "nico.mid_start_guard.v2"
_PATCH_MARKER = "_nico_mid_start_guard_v2"
_LOCAL_START_LOCK = threading.RLock()
_ACTIVE_LIFECYCLE_STATUSES = {"queued", "running", "starting", "pending"}
_TERMINAL_FAILURE_STATUSES = {"failed", "blocked", "error", "rejected", "cancelled"}


def _payload(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model or {})


def _canonical_repository(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("https://github.com/"):
        text = text[len("https://github.com/"):]
    if text.startswith("http://github.com/"):
        text = text[len("http://github.com/"):]
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    if text.endswith(".git"):
        text = text[:-4]
    return text


def _record_repository(record: dict[str, Any]) -> str:
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    return _canonical_repository(
        record.get("repository")
        or request.get("repository")
        or request.get("target")
        or response.get("repository")
    )


def _final_artifacts_ready(payload: dict[str, Any]) -> bool:
    approval = payload.get("approval_request") if isinstance(payload.get("approval_request"), dict) else {}
    return (
        str(payload.get("status") or "").lower() in {"complete", "completed"}
        and str(payload.get("report_generation_status") or "").lower() == "complete"
        and bool(approval.get("approval_id"))
    )


def _candidate_records(customer_id: str, project_id: str, repository: str) -> list[dict[str, Any]]:
    records = STORE.list("assessment_runs", customer_id=customer_id, project_id=project_id)
    matching = [
        record
        for record in records
        if isinstance(record, dict)
        and str(record.get("workflow") or "") == "mid_assessment"
        and _record_repository(record) == repository
    ]
    return sorted(
        matching,
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )


def _live_state(record: dict[str, Any], customer_id: str, project_id: str) -> dict[str, Any] | None:
    run_id = str(record.get("run_id") or "")
    if not run_id.startswith("midrun_"):
        return None
    try:
        from nico.mid_live_status_api import mid_live_status_response

        return mid_live_status_response(run_id, customer_id=customer_id, project_id=project_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise
    except Exception:
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        fallback = deepcopy(response)
        fallback.setdefault("run_id", run_id)
        fallback.setdefault("status", record.get("status") or "unknown")
        fallback["start_guard_live_status_unavailable"] = True
        return fallback


def _blocks_new_start(state: dict[str, Any]) -> bool:
    status = str(state.get("status") or "").lower()
    scanner = state.get("scanner") if isinstance(state.get("scanner"), dict) else {}
    scanner_status = str(scanner.get("status") or "").lower()
    if _final_artifacts_ready(state):
        return False
    if bool(state.get("recovery_required")):
        return True
    if status in _ACTIVE_LIFECYCLE_STATUSES:
        return True
    if scanner_status in {"queued", "running", "recovery_required"}:
        return True
    if bool(state.get("continuation_required")):
        return True
    if status in _TERMINAL_FAILURE_STATUSES:
        return False
    # An incomplete durable Mid record with an unknown lifecycle state is kept
    # fail-closed. The operator can recover or explicitly terminalize it rather
    # than starting another scanner against the same repository.
    return bool(str(state.get("run_id") or "").startswith("midrun_"))


def _guarded_reuse(state: dict[str, Any], other_active_run_ids: list[str]) -> dict[str, Any]:
    output = deepcopy(state)
    output["idempotent_start_reuse"] = True
    output["duplicate_start_prevented"] = True
    output["start_guard"] = {
        "version": MID_START_GUARD_VERSION,
        "decision": "reuse_existing_exact_run",
        "run_id": output.get("run_id") or "",
        "other_active_run_ids": other_active_run_ids,
        "operator_action": "Continue or recover the existing exact run. Do not start another Mid scanner for the same repository and scope.",
        "read_only_repository": True,
        "cross_worker_serialization": True,
    }
    output.setdefault("human_review_required", True)
    output.setdefault("client_ready", False)
    return output


def _lock_wait_seconds() -> float:
    try:
        configured = float(os.getenv("NICO_MID_START_LOCK_WAIT_SECONDS", "15"))
    except (TypeError, ValueError):
        configured = 15.0
    return max(1.0, min(configured, 30.0))


def _lock_acquired(row: Any) -> bool:
    if isinstance(row, dict):
        return bool(next(iter(row.values()), False))
    if isinstance(row, (tuple, list)):
        return bool(row[0]) if row else False
    return bool(row)


def _lock_failure_detail(code: str, message: str, failure_type: str = "") -> dict[str, Any]:
    return {
        "status": "temporarily_unavailable",
        "code": code,
        "message": message,
        "failure_type": failure_type[:80],
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


@contextmanager
def _serialized_start(lock_key: str) -> Iterator[None]:
    """Serialize same-target starts in-process and across Postgres web workers."""

    with _LOCAL_START_LOCK:
        status = STORE.status() if hasattr(STORE, "status") else {}
        adapter = getattr(STORE, "adapter", STORE)
        connect = getattr(adapter, "_connect", None)
        if str(status.get("adapter") or status.get("mode") or "") != "postgres" or not callable(connect):
            yield
            return

        connection = None
        acquired = False
        try:
            connection = connect()
            deadline = time.monotonic() + _lock_wait_seconds()
            while time.monotonic() < deadline and not acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (lock_key,))
                    acquired = _lock_acquired(cursor.fetchone())
                if not acquired:
                    time.sleep(0.1)
            if not acquired:
                raise HTTPException(
                    status_code=503,
                    detail=_lock_failure_detail(
                        "mid_start_guard_busy",
                        "Another request is establishing or reconciling the same Mid assessment. Retry the exact request; NICO will not start a duplicate scanner.",
                    ),
                )
            yield
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=_lock_failure_detail(
                    "mid_start_guard_unavailable",
                    "NICO could not verify cross-worker start serialization, so it refused to start a potentially duplicate Mid scanner.",
                    type(exc).__name__,
                ),
            ) from exc
        finally:
            if connection is not None:
                try:
                    if acquired:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", (lock_key,))
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass


def install_mid_start_guard() -> dict[str, Any]:
    from nico import mid_assessment_api as api

    current: Callable[..., dict[str, Any]] = api.mid_assessment_response
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_START_GUARD_VERSION}

    @wraps(current)
    def guarded_start(req: Any) -> dict[str, Any]:
        request = _payload(req)
        customer_id = str(request.get("customer_id") or "default_customer")
        project_id = str(request.get("project_id") or "default_project")
        repository = _canonical_repository(request.get("repository") or request.get("target"))
        if not repository:
            return current(req)

        lock_key = f"nico:mid-start:{customer_id}:{project_id}:{repository}"
        with _serialized_start(lock_key):
            active_states: list[dict[str, Any]] = []
            for record in _candidate_records(customer_id, project_id, repository):
                state = _live_state(record, customer_id, project_id)
                if state and _blocks_new_start(state):
                    active_states.append(state)

            if active_states:
                selected = active_states[0]
                selected_run_id = str(selected.get("run_id") or "")
                others = [
                    str(item.get("run_id") or "")
                    for item in active_states[1:]
                    if str(item.get("run_id") or "") and str(item.get("run_id") or "") != selected_run_id
                ]
                return _guarded_reuse(selected, others)

            return current(req)

    setattr(guarded_start, _PATCH_MARKER, True)
    setattr(guarded_start, "_nico_previous", current)
    api.mid_assessment_response = guarded_start
    return {
        "status": "installed",
        "version": MID_START_GUARD_VERSION,
        "server_side_duplicate_prevention": True,
        "same_scope_repository_reuse": True,
        "cross_worker_postgres_advisory_lock": True,
        "fail_closed_when_serialization_unavailable": True,
        "recovery_required_blocks_new_start": True,
        "completed_or_terminal_failed_run_allows_new_start": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_START_GUARD_VERSION",
    "install_mid_start_guard",
]
