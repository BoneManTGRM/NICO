from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from fastapi import HTTPException

from nico import lifecycle_status_hardening as hardening

EXPRESS_STATUS_LIVENESS_VERSION = "nico.express_status_liveness.v1"
_PATCH_MARKER = "_nico_express_status_liveness_v1"
_EXPRESS_STALE_SECONDS = 300
_SCANNER_STALE_SECONDS = 600


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _linked_scanner(record: dict[str, Any], response: dict[str, Any]) -> tuple[dict[str, Any], float | None]:
    embedded = _record(response.get("scanner"))
    scan_id = str(
        response.get("scan_id")
        or embedded.get("scan_id")
        or record.get("scan_id")
        or _record(record.get("request")).get("scan_id")
        or ""
    )
    if not scan_id:
        return embedded, hardening._age_seconds(embedded.get("heartbeat_at") or embedded.get("updated_at"))
    durable = hardening.STORE.get("scanner_runs", scan_id)
    scanner = hardening._safe_scan(durable) if isinstance(durable, dict) else embedded
    scanner.setdefault("scan_id", scan_id)
    heartbeat = scanner.get("heartbeat_at") or scanner.get("updated_at")
    return scanner, hardening._age_seconds(heartbeat)


def _fresh_active_scanner(scanner: dict[str, Any], age_seconds: float | None) -> bool:
    status = str(scanner.get("status") or "").lower()
    return status in {"queued", "running", "starting", "pending"} and age_seconds is not None and age_seconds <= _SCANNER_STALE_SECONDS


def _lifecycle_metadata(
    response: dict[str, Any],
    *,
    heartbeat_at: Any,
    heartbeat_age: float | None,
    worker_started: bool,
    scanner: dict[str, Any],
    scanner_age: float | None,
    scanner_corroborated: bool,
) -> dict[str, Any]:
    return {
        "version": EXPRESS_STATUS_LIVENESS_VERSION,
        "mode": "durable_exact_run_read",
        "heartbeat_at": heartbeat_at or "",
        "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
        "worker_started": worker_started,
        "worker_started_at": response.get("worker_started_at") or "",
        "worker_process_id": response.get("worker_process_id"),
        "worker_thread": response.get("worker_thread") or "",
        "backend_stage": response.get("backend_stage") or "",
        "scanner_status": scanner.get("status") or "not_started",
        "scanner_heartbeat_age_seconds": round(scanner_age, 1) if scanner_age is not None else None,
        "scanner_liveness_corroborated": scanner_corroborated,
        "process_local_active_set_required": False,
        "status_read_is_terminal_write": False,
        "request_validation_422_possible": False,
    }


def _nonterminal_liveness_projection(
    response: dict[str, Any],
    *,
    code: str,
    message: str,
    heartbeat_at: Any,
    heartbeat_age: float | None,
    scanner: dict[str, Any],
    scanner_age: float | None,
) -> dict[str, Any]:
    projected = deepcopy(response)
    projected.update(
        {
            "status": "temporarily_unavailable",
            "code": code,
            "message": message,
            "recovery_required": True,
            "recovery_path": "/operations/recovery",
            "status_read_only": True,
            "terminal_state_written": False,
            "duplicate_start_allowed": False,
            "human_review_required": True,
            "client_ready": False,
        }
    )
    projected["scanner"] = scanner
    projected["lifecycle_status"] = _lifecycle_metadata(
        projected,
        heartbeat_at=heartbeat_at,
        heartbeat_age=heartbeat_age,
        worker_started=bool(response.get("worker_started")),
        scanner=scanner,
        scanner_age=scanner_age,
        scanner_corroborated=False,
    )
    return projected


def install_express_status_liveness_patch() -> dict[str, Any]:
    current: Callable[[str, str, str], dict[str, Any]] = hardening._express_status_response
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": EXPRESS_STATUS_LIVENESS_VERSION,
            "scanner_liveness_corroboration": True,
            "status_read_terminal_write": False,
        }

    def resilient_status_response(run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
        record = hardening.STORE.get("assessment_runs", run_id)
        if not isinstance(record, dict) or str(record.get("workflow") or "") != "express":
            return current(run_id, customer_id, project_id)
        if not hardening._scope_matches(record, customer_id, project_id):
            return current(run_id, customer_id, project_id)

        response = hardening._safe_retained_response(record)
        status = str(response.get("status") or record.get("status") or "unknown").lower()
        if status not in hardening._ACTIVE:
            return current(run_id, customer_id, project_id)

        response["run_id"] = run_id
        response["customer_id"] = customer_id
        response["project_id"] = project_id
        response.setdefault("assessment_type", "express")
        response.setdefault("service_tier", "express")
        response.setdefault("human_review_required", True)
        response["client_ready"] = False
        response["status"] = "running" if status != "queued" else "queued"

        heartbeat_at = response.get("heartbeat_at") or record.get("heartbeat_at") or response.get("updated_at") or record.get("updated_at")
        heartbeat_age = hardening._age_seconds(heartbeat_at)
        created_at = response.get("created_at") or record.get("created_at") or response.get("updated_at") or record.get("updated_at")
        run_age = hardening._age_seconds(created_at)
        worker_started = bool(response.get("worker_started"))
        scanner, scanner_age = _linked_scanner(record, response)
        scanner_corroborated = _fresh_active_scanner(scanner, scanner_age)
        if scanner:
            response["scanner"] = scanner

        response["lifecycle_status"] = _lifecycle_metadata(
            response,
            heartbeat_at=heartbeat_at,
            heartbeat_age=heartbeat_age,
            worker_started=worker_started,
            scanner=scanner,
            scanner_age=scanner_age,
            scanner_corroborated=scanner_corroborated,
        )

        if scanner_corroborated:
            return response
        if not worker_started and run_age is not None and run_age > hardening._EXPRESS_WORKER_START_GRACE_SECONDS:
            detail = _nonterminal_liveness_projection(
                response,
                code="express_worker_start_unconfirmed",
                message="The accepted Express worker start handshake is not yet confirmed. The exact run remains preserved and no terminal state was written by this status read.",
                heartbeat_at=heartbeat_at,
                heartbeat_age=heartbeat_age,
                scanner=scanner,
                scanner_age=scanner_age,
            )
            raise HTTPException(status_code=503, detail=detail)
        if heartbeat_age is None or heartbeat_age <= _EXPRESS_STALE_SECONDS:
            return response

        detail = _nonterminal_liveness_projection(
            response,
            code="express_worker_liveness_unconfirmed",
            message="The Express heartbeat is stale and no fresh scanner heartbeat corroborates execution. The exact run remains preserved for recovery; this status read did not mark it interrupted.",
            heartbeat_at=heartbeat_at,
            heartbeat_age=heartbeat_age,
            scanner=scanner,
            scanner_age=scanner_age,
        )
        raise HTTPException(status_code=503, detail=detail)

    setattr(resilient_status_response, _PATCH_MARKER, True)
    setattr(resilient_status_response, "_nico_previous", current)
    hardening._express_status_response = resilient_status_response
    return {
        "status": "installed",
        "version": EXPRESS_STATUS_LIVENESS_VERSION,
        "scanner_liveness_corroboration": True,
        "express_stale_seconds": _EXPRESS_STALE_SECONDS,
        "scanner_stale_seconds": _SCANNER_STALE_SECONDS,
        "status_read_terminal_write": False,
        "automatic_resume": False,
        "replacement_run": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "EXPRESS_STATUS_LIVENESS_VERSION",
    "install_express_status_liveness_patch",
]
