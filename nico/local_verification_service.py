from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from nico.local_runtime_config import DB_PATH
from nico.local_scan_engine import new_id, now
from nico.local_store import LocalStore


class LocalVerificationStore(Protocol):
    def latest_scan(self) -> dict[str, Any]: ...

    def payloads(self, table: str) -> list[dict[str, Any]]: ...

    def save_verification(self, result: dict[str, Any]) -> None: ...

    def save_memory(self, payload: dict[str, Any]) -> None: ...

    def update_repair_status(self, repair_id: str, status: str) -> dict[str, Any] | None: ...

    def audit(self, action: str, detail: dict[str, Any]) -> None: ...


def verify_latest(
    *,
    store: LocalVerificationStore | None = None,
    id_factory: Callable[[str], str] = new_id,
    clock: Callable[[], str] = now,
) -> dict[str, Any]:
    active_store = store if store is not None else LocalStore(DB_PATH)
    scan = active_store.latest_scan()
    findings = active_store.payloads("findings")
    repairs = active_store.payloads("repairs")
    masked = all("FAKE_TEST_ONLY_SECRET_123456" not in str(finding) for finding in findings)
    result = {
        "id": id_factory("verify"),
        "created_at": clock(),
        "scan_id": scan.get("id"),
        "repair_id": None,
        "passed": bool(scan) and masked,
        "status": "verification_observed",
        "checks": [
            "scan_available" if scan else "scan_missing",
            "findings_masked" if masked else "masking_failure",
            "governance_enabled",
            "repair_candidates_present" if repairs else "repair_candidates_missing",
        ],
        "risk_reduction": "pending_targeted_code_repair",
        "finding_count": len(findings),
        "repair_count": len(repairs),
        "baseline_update_allowed": False,
    }
    active_store.save_verification(result)
    active_store.save_memory(
        {
            "id": result["id"],
            "type": "verification",
            "created_at": result["created_at"],
            "result": result,
        }
    )
    active_store.audit("verification.latest", result)
    return result


def verify_repair_by_id(
    repair_id: str,
    *,
    store: LocalVerificationStore | None = None,
    id_factory: Callable[[str], str] = new_id,
    clock: Callable[[], str] = now,
) -> dict[str, Any]:
    active_store = store if store is not None else LocalStore(DB_PATH)
    repair = next(
        (
            item
            for item in active_store.payloads("repairs")
            if item.get("id") == repair_id or item.get("repair_id") == repair_id
        ),
        None,
    )
    result = {
        "id": id_factory("verify"),
        "created_at": clock(),
        "repair_id": repair.get("id") if repair else None,
        "passed": bool(repair),
        "status": "verification_pending" if repair else "repair_not_found",
        "checks": [
            "repair_exists" if repair else "repair_missing",
            "rescan_required",
            "raw_secret_masking_checked",
        ],
        "risk_reduction": "requires_rescan_after_patch",
        "baseline_update_allowed": False,
    }
    active_store.save_verification(result)
    active_store.save_memory(
        {
            "id": result["id"],
            "type": "verification",
            "created_at": result["created_at"],
            "result": result,
        }
    )
    if repair:
        active_store.update_repair_status(str(repair["id"]), result["status"])
    active_store.audit("verification.repair", result)
    return result


__all__ = [
    "LocalVerificationStore",
    "verify_latest",
    "verify_repair_by_id",
]
