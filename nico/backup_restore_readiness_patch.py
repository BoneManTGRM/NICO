from __future__ import annotations

from typing import Any, Callable

import nico.operations_readiness as operations_readiness
from nico.backup_restore_readiness import (
    REQUIRED_BACKUP_RESTORE_ROUTE_NAMES,
    backup_restore_status,
)

BACKUP_RESTORE_READINESS_VERSION = "nico.backup_restore_operations_readiness.v1"
_INSTALLED = False
_ORIGINAL_BUILD: Callable[..., dict[str, Any]] | None = None


def _recompute(base: dict[str, Any]) -> None:
    checks = [item for item in base.get("checks") or [] if isinstance(item, dict)]
    required_failures = [item for item in checks if item.get("required") and not item.get("passed")]
    advisory_failures = [item for item in checks if not item.get("required") and not item.get("passed")]
    status = "blocked" if required_failures else "degraded" if advisory_failures else "ready"
    base["status"] = status
    base["operational_ready"] = status == "ready"
    base["required_checks"] = sum(1 for item in checks if item.get("required"))
    base["required_passed"] = sum(1 for item in checks if item.get("required") and item.get("passed"))
    base["advisory_checks"] = sum(1 for item in checks if not item.get("required"))
    base["advisory_passed"] = sum(1 for item in checks if not item.get("required") and item.get("passed"))
    base["blockers"] = [str(item.get("id") or "") for item in required_failures]
    base["warnings"] = [str(item.get("id") or "") for item in advisory_failures]
    if status == "blocked":
        labels = ", ".join(str(item.get("label") or item.get("id")) for item in required_failures)
        base["next_action"] = f"Fix required operational blockers before accepting trusted production work: {labels}."
    elif status == "degraded":
        labels = ", ".join(str(item.get("label") or item.get("id")) for item in advisory_failures)
        base["next_action"] = f"Core operation is available, but resolve advisory warnings before full operator use: {labels}."


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
            "status": "blocked",
            "backup_restore_ready": False,
            "persistence_available": persistence_available,
            "blockers": [
                "backup_evidence_missing",
                "restore_drill_missing",
            ] if persistence_available else ["durable_postgres_required"],
            "warnings": [],
            "latest_backup": {"present": False},
            "latest_restore_drill": {"present": False},
        }
    return backup_restore_status()


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
    backup_restore: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _ORIGINAL_BUILD is None:
        raise RuntimeError("Backup/restore readiness patch was not installed.")
    routes = {str(item).strip() for item in route_inventory if str(item).strip()}
    base = _ORIGINAL_BUILD(
        sorted(routes),
        deployment=deployment,
        storage=storage,
        features=features,
        report_truth=report_truth,
        runtime=runtime,
        storage_schema=storage_schema,
        scanner_recovery=scanner_recovery,
        assessment_recovery=assessment_recovery,
    )
    storage_payload = storage if isinstance(storage, dict) else base.get("storage") or {}
    evidence = _payload_for_call(
        storage_argument_supplied=storage is not None,
        persistence_available=bool(storage_payload.get("persistence_available")),
        injected=backup_restore,
    )
    ready = bool(evidence.get("status") == "ready" and evidence.get("backup_restore_ready") is True)
    check = {
        "id": "backup_restore_verified",
        "label": "Current backup and isolated restore-drill evidence",
        "required": False,
        "passed": ready,
        "status": "passed" if ready else "failed",
        "observed": {
            "status": evidence.get("status") or "unavailable",
            "backup_present": bool((evidence.get("latest_backup") or {}).get("present")),
            "restore_drill_present": bool((evidence.get("latest_restore_drill") or {}).get("present")),
            "blockers": list(evidence.get("blockers") or [])[:20],
            "warnings": list(evidence.get("warnings") or [])[:20],
        },
        "expected": {
            "status": "ready",
            "current_successful_backup": True,
            "current_successful_isolated_restore_drill": True,
        },
        "remediation": "" if ready else (
            "Review /operations/backup-restore, record real bounded backup evidence, and record a successful isolated non-production restore drill. Do not treat provider documentation as operational proof."
        ),
    }
    checks = [
        item
        for item in base.get("checks") or []
        if isinstance(item, dict) and item.get("id") != "backup_restore_verified"
    ]
    checks.append(check)
    base["checks"] = checks
    base["backup_restore"] = {
        "status": evidence.get("status") or "unavailable",
        "ready": ready,
        "latest_backup": evidence.get("latest_backup") or {"present": False},
        "latest_restore_drill": evidence.get("latest_restore_drill") or {"present": False},
        "blockers": list(evidence.get("blockers") or [])[:20],
        "warnings": list(evidence.get("warnings") or [])[:20],
        "automatic_backup": False,
        "automatic_restore": False,
        "client_delivery_allowed": False,
    }
    missing_routes = sorted(operations_readiness.REQUIRED_OPERATION_ROUTES - routes)
    base["missing_routes"] = missing_routes
    for item in checks:
        if item.get("id") == "required_routes_registered":
            item["passed"] = not missing_routes
            item["status"] = "passed" if not missing_routes else "failed"
            item["observed"] = {"registered": len(routes), "missing": missing_routes}
            item["expected"] = sorted(operations_readiness.REQUIRED_OPERATION_ROUTES)
            item["remediation"] = "" if not missing_routes else (
                "Register every required operations, assessment, scanner, observability, alert, storage-schema, recovery, and backup/restore route in the production application."
            )
    _recompute(base)
    base["backup_restore_readiness_version"] = BACKUP_RESTORE_READINESS_VERSION
    return base


def install_backup_restore_readiness_patch() -> dict[str, Any]:
    global _INSTALLED, _ORIGINAL_BUILD
    operations_readiness.REQUIRED_OPERATION_ROUTES.update(REQUIRED_BACKUP_RESTORE_ROUTE_NAMES)
    if _INSTALLED:
        return {
            "installed": True,
            "idempotent_reuse": True,
            "version": BACKUP_RESTORE_READINESS_VERSION,
        }
    _ORIGINAL_BUILD = operations_readiness.build_operations_readiness
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
        "version": BACKUP_RESTORE_READINESS_VERSION,
        "required_routes": sorted(REQUIRED_BACKUP_RESTORE_ROUTE_NAMES),
    }


__all__ = [
    "BACKUP_RESTORE_READINESS_VERSION",
    "build_operations_readiness",
    "install_backup_restore_readiness_patch",
]
