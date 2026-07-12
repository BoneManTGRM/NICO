from __future__ import annotations

from typing import Any

import nico.operations_readiness as operations_readiness
from nico.assessment_recovery import (
    REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES,
    assessment_recovery_status,
)

ASSESSMENT_RECOVERY_READINESS_VERSION = "nico.assessment_recovery_readiness.v1"
_INSTALLED = False
_ORIGINAL_BUILD = operations_readiness.build_operations_readiness


def _payload_for_call(
    *,
    storage_argument_supplied: bool,
    persistence_available: bool,
    injected: dict[str, Any] | None,
) -> dict[str, Any]:
    if injected is not None:
        return injected if isinstance(injected, dict) else {}
    if storage_argument_supplied:
        return {
            "status": "clear" if persistence_available else "unavailable",
            "clear": persistence_available,
            "persistence_available": persistence_available,
            "recovery_required": 0 if persistence_available else None,
            "stale_active": 0 if persistence_available else None,
            "active": 0 if persistence_available else None,
            "blockers": [] if persistence_available else ["durable_postgres_required"],
        }
    return assessment_recovery_status()


def _recompute(base: dict[str, Any]) -> None:
    checks = [item for item in base.get("checks") or [] if isinstance(item, dict)]
    required_failures = [
        item for item in checks if item.get("required") and not item.get("passed")
    ]
    advisory_failures = [
        item for item in checks if not item.get("required") and not item.get("passed")
    ]
    status = "blocked" if required_failures else "degraded" if advisory_failures else "ready"
    base["status"] = status
    base["operational_ready"] = status == "ready"
    base["required_checks"] = sum(1 for item in checks if item.get("required"))
    base["required_passed"] = sum(
        1 for item in checks if item.get("required") and item.get("passed")
    )
    base["advisory_checks"] = sum(1 for item in checks if not item.get("required"))
    base["advisory_passed"] = sum(
        1 for item in checks if not item.get("required") and item.get("passed")
    )
    base["blockers"] = [str(item.get("id") or "") for item in required_failures]
    base["warnings"] = [str(item.get("id") or "") for item in advisory_failures]
    if status == "blocked":
        labels = ", ".join(
            str(item.get("label") or item.get("id")) for item in required_failures
        )
        base["next_action"] = (
            f"Fix required operational blockers before accepting trusted production work: {labels}."
        )
    elif status == "degraded":
        labels = ", ".join(
            str(item.get("label") or item.get("id")) for item in advisory_failures
        )
        base["next_action"] = (
            f"Core operation is available, but resolve advisory warnings before full operator use: {labels}."
        )


def build_operations_readiness(
    route_inventory: list[str] | set[str] | tuple[str, ...],
    *,
    deployment: dict[str, Any] | None = None,
    storage: dict[str, Any] | None = None,
    features: dict[str, Any] | None = None,
    report_truth: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    storage_schema: dict[str, Any] | None = None,
    scanner_recovery: dict[str, Any] | None = None,
    assessment_recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routes = {str(item).strip() for item in route_inventory if str(item).strip()}
    routes.update(REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES & routes)
    base = _ORIGINAL_BUILD(
        sorted(routes),
        deployment=deployment,
        storage=storage,
        features=features,
        report_truth=report_truth,
        runtime=runtime,
        storage_schema=storage_schema,
        scanner_recovery=scanner_recovery,
    )
    storage_payload = storage if isinstance(storage, dict) else base.get("storage") or {}
    persistence_available = bool(storage_payload.get("persistence_available"))
    recovery = _payload_for_call(
        storage_argument_supplied=storage is not None,
        persistence_available=persistence_available,
        injected=assessment_recovery,
    )
    clear = bool(
        recovery.get("status") == "clear"
        and recovery.get("clear") is True
        and int(recovery.get("recovery_required") or 0) == 0
        and int(recovery.get("stale_active") or 0) == 0
    )
    check = {
        "id": "assessment_recovery_queue_clear",
        "label": "Interrupted Mid and Full recovery queue",
        "required": False,
        "passed": clear,
        "status": "passed" if clear else "failed",
        "observed": {
            "status": recovery.get("status") or "unavailable",
            "recovery_required": recovery.get("recovery_required"),
            "stale_active": recovery.get("stale_active"),
            "active": recovery.get("active"),
            "blockers": list(recovery.get("blockers") or [])[:20]
            if isinstance(recovery.get("blockers"), list)
            else [],
        },
        "expected": {
            "status": "clear",
            "recovery_required": 0,
            "stale_active": 0,
        },
        "remediation": ""
        if clear
        else "Review /operations/recovery/assessments and resume only authorized interrupted runs through the same-run recovery endpoint.",
    }
    checks = [
        item
        for item in base.get("checks") or []
        if isinstance(item, dict)
        and item.get("id") != "assessment_recovery_queue_clear"
    ]
    checks.append(check)
    base["checks"] = checks
    base["assessment_recovery"] = {
        "status": recovery.get("status") or "unavailable",
        "clear": clear,
        "recovery_required": recovery.get("recovery_required"),
        "stale_active": recovery.get("stale_active"),
        "active": recovery.get("active"),
        "blockers": list(recovery.get("blockers") or [])[:20]
        if isinstance(recovery.get("blockers"), list)
        else [],
        "automatic_resume": False,
    }
    missing_routes = sorted(
        operations_readiness.REQUIRED_OPERATION_ROUTES - routes
    )
    base["missing_routes"] = missing_routes
    for item in checks:
        if item.get("id") == "required_routes_registered":
            item["passed"] = not missing_routes
            item["status"] = "passed" if not missing_routes else "failed"
            item["observed"] = {
                "registered": len(routes),
                "missing": missing_routes,
            }
            item["expected"] = sorted(
                operations_readiness.REQUIRED_OPERATION_ROUTES
            )
            item["remediation"] = "" if not missing_routes else (
                "Register every required operations, assessment, scanner, observability, alert, storage-schema, and recovery route in the production application."
            )
    _recompute(base)
    base["assessment_recovery_readiness_version"] = (
        ASSESSMENT_RECOVERY_READINESS_VERSION
    )
    return base


def install_assessment_recovery_readiness_patch() -> dict[str, Any]:
    global _INSTALLED
    operations_readiness.REQUIRED_OPERATION_ROUTES.update(
        REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES
    )
    if _INSTALLED:
        return {
            "installed": True,
            "idempotent_reuse": True,
            "version": ASSESSMENT_RECOVERY_READINESS_VERSION,
        }
    operations_readiness.build_operations_readiness = build_operations_readiness
    try:
        import nico.operations_readiness_api as readiness_api

        readiness_api.build_operations_readiness = build_operations_readiness
    except Exception:
        pass
    _INSTALLED = True
    return {
        "installed": True,
        "idempotent_reuse": False,
        "version": ASSESSMENT_RECOVERY_READINESS_VERSION,
        "required_routes": sorted(REQUIRED_ASSESSMENT_RECOVERY_ROUTE_NAMES),
    }


__all__ = [
    "ASSESSMENT_RECOVERY_READINESS_VERSION",
    "build_operations_readiness",
    "install_assessment_recovery_readiness_patch",
]
