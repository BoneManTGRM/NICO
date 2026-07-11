from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from nico import approved_delivery_access as access_store
from nico.admin_security import require_admin_write
from nico.approved_delivery_access import list_approved_delivery_access
from nico.approved_delivery_acknowledgments import list_delivery_acknowledgments
from nico.approved_delivery_receipts import list_delivery_receipts
from nico.approved_delivery_recovery import approved_delivery_status
from nico.approved_delivery_storage_policy import delivery_storage_readiness
from nico.storage import STORE

DEFAULT_RECONCILIATION_GRACE_SECONDS = 300
MAX_RECONCILIATION_GRACE_SECONDS = 3600


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
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


def _grace_seconds(value: Any = None) -> int:
    configured = value if value is not None else os.getenv("NICO_DELIVERY_RECONCILIATION_GRACE_SECONDS", DEFAULT_RECONCILIATION_GRACE_SECONDS)
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = DEFAULT_RECONCILIATION_GRACE_SECONDS
    return max(0, min(MAX_RECONCILIATION_GRACE_SECONDS, parsed))


def _check(check_id: str, passed: bool, message: str, evidence: Any = None) -> dict[str, Any]:
    result = {"id": check_id, "passed": bool(passed), "message": message}
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _ledger_data(run_id: str, customer_id: str, project_id: str, admin_token: str) -> dict[str, Any]:
    access_result = list_approved_delivery_access(run_id, customer_id, project_id, admin_token=admin_token)
    receipt_result = list_delivery_receipts(run_id, customer_id, project_id, admin_token=admin_token)
    acknowledgment_result = list_delivery_acknowledgments(run_id, customer_id, project_id, admin_token=admin_token)
    return {
        "access_result": access_result,
        "receipt_result": receipt_result,
        "acknowledgment_result": acknowledgment_result,
        "access": access_result.get("access") if isinstance(access_result.get("access"), list) else [],
        "receipts": receipt_result.get("receipts") if isinstance(receipt_result.get("receipts"), list) else [],
        "acknowledgments": acknowledgment_result.get("acknowledgments") if isinstance(acknowledgment_result.get("acknowledgments"), list) else [],
    }


def _counts_by_access(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        access_id = str(item.get("access_id") or "")
        if access_id:
            counts[access_id] = counts.get(access_id, 0) + 1
    return counts


def approved_delivery_operational_readiness(
    run_or_report_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
) -> dict[str, Any]:
    """Evaluate the complete approved-delivery lifecycle without mutating it."""

    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "ready": False, "error": "Admin authentication is required to inspect delivery readiness.", "admin_write": admin}
    lookup = str(run_or_report_id or "").strip()
    if not lookup:
        return {"status": "blocked", "ready": False, "error": "run_id or report_id is required"}

    storage = delivery_storage_readiness()
    recovered = approved_delivery_status(lookup, customer_id=customer_id, project_id=project_id, include_pdf=False)
    run_id = str(recovered.get("run_id") or lookup)
    ledger = _ledger_data(run_id, customer_id, project_id, admin_token)
    access = [item for item in ledger["access"] if isinstance(item, dict)]
    receipts = [item for item in ledger["receipts"] if isinstance(item, dict)]
    acknowledgments = [item for item in ledger["acknowledgments"] if isinstance(item, dict)]
    approval = recovered.get("approval") if isinstance(recovered.get("approval"), dict) else {}
    delivery = recovered.get("approved_delivery") if isinstance(recovered.get("approved_delivery"), dict) else {}

    access_ids = {str(item.get("access_id") or "") for item in access if item.get("access_id")}
    receipt_ids = {str(item.get("receipt_id") or "") for item in receipts if item.get("receipt_id")}
    receipt_counts = _counts_by_access(receipts)
    invalid_receipts = [str(item.get("receipt_id") or "unknown") for item in receipts if not item.get("verified")]
    invalid_acknowledgments = [str(item.get("acknowledgment_id") or "unknown") for item in acknowledgments if not item.get("verified")]
    orphan_receipt_access = sorted({str(item.get("access_id") or "") for item in receipts if str(item.get("access_id") or "") not in access_ids})
    orphan_ack_receipts = sorted({str(item.get("receipt_id") or "") for item in acknowledgments if str(item.get("receipt_id") or "") not in receipt_ids})

    consumption_mismatches: list[dict[str, Any]] = []
    repairable_orphans: list[dict[str, Any]] = []
    for item in access:
        access_id = str(item.get("access_id") or "")
        recorded_downloads = int(item.get("download_count") or 0)
        verified_receipts = int(receipt_counts.get(access_id, 0))
        if recorded_downloads != verified_receipts:
            mismatch = {
                "access_id": access_id,
                "recipient_label": item.get("recipient_label") or "",
                "download_count": recorded_downloads,
                "verified_receipt_count": verified_receipts,
                "difference": recorded_downloads - verified_receipts,
                "last_redeemed_at": item.get("last_redeemed_at") or "",
            }
            consumption_mismatches.append(mismatch)
            if recorded_downloads > verified_receipts:
                repairable_orphans.append(mismatch)

    approval_decision = approval.get("review_decision") if isinstance(approval.get("review_decision"), dict) else {}
    ledger_loaded = all(
        ledger[key].get("status") == "ok"
        for key in ("access_result", "receipt_result", "acknowledgment_result")
    )
    hash_fields_valid = all(
        len(str(delivery.get(key) or "")) == 64
        for key in ("pdf_sha256", "source_draft_pdf_sha256", "approval_identity_sha256")
    )
    checks = [
        _check("durable_storage", bool(storage.get("ready")), "Required delivery storage is ready.", storage),
        _check("approved_artifact", bool(recovered.get("verified")), "The approved Full Assessment passes current identity and integrity verification.", recovered.get("verification") or {}),
        _check("human_approval", approval.get("status") == "approved" and approval_decision.get("client_delivery_allowed") is True, "An immutable human approval authorizes client delivery."),
        _check("artifact_hashes", hash_fields_valid, "Approved PDF, source draft, and approval identity SHA-256 values are present."),
        _check("ledgers_loaded", ledger_loaded, "Access, receipt, and acknowledgment ledgers loaded for the exact scope."),
        _check("receipt_integrity", not invalid_receipts, "Every delivery receipt passes canonical hash verification.", invalid_receipts),
        _check("acknowledgment_integrity", not invalid_acknowledgments, "Every client acknowledgment passes canonical hash verification.", invalid_acknowledgments),
        _check("receipt_access_binding", not orphan_receipt_access, "Every receipt is bound to an access grant in this scope.", orphan_receipt_access),
        _check("acknowledgment_receipt_binding", not orphan_ack_receipts, "Every acknowledgment is bound to a delivery receipt in this scope.", orphan_ack_receipts),
        _check("download_receipt_reconciliation", not consumption_mismatches, "Every consumed download has exactly one verified delivery receipt.", consumption_mismatches),
    ]
    blockers = [item["message"] for item in checks if not item["passed"]]
    ready = not blockers
    if acknowledgments:
        lifecycle = "acknowledged"
    elif receipts:
        lifecycle = "delivered"
    elif access:
        lifecycle = "shared"
    elif recovered.get("verified"):
        lifecycle = "approved"
    else:
        lifecycle = "blocked"

    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "lifecycle": lifecycle,
        "run_id": run_id,
        "report_id": recovered.get("report_id") or "",
        "approval_id": recovered.get("approval_id") or "",
        "customer_id": customer_id,
        "project_id": project_id,
        "checks": checks,
        "blockers": blockers,
        "summary": {
            "access_grant_count": len(access),
            "download_count": sum(int(item.get("download_count") or 0) for item in access),
            "verified_receipt_count": sum(1 for item in receipts if item.get("verified")),
            "verified_acknowledgment_count": sum(1 for item in acknowledgments if item.get("verified")),
            "consumption_mismatch_count": len(consumption_mismatches),
        },
        "repairable_orphaned_consumptions": repairable_orphans,
        "critical_over_receipting": [item for item in consumption_mismatches if item["difference"] < 0],
        "storage_readiness": storage,
        "rule": "Operational readiness requires verified approval, durable hosted storage, intact ledgers, and a one-to-one match between consumed downloads and verified delivery receipts.",
    }


def _conditional_repair_access(
    access_id: str,
    expected_count: int,
    expected_last_redeemed_at: str,
    repaired_count: int,
    repaired_last_redeemed_at: str,
    repaired_at: str,
) -> dict[str, Any] | None:
    if access_store._postgres_available():
        with access_store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approved_delivery_access
                    SET download_count=%s,
                        updated_at=%s,
                        payload=jsonb_set(
                          jsonb_set(payload, '{download_count}', to_jsonb(%s::integer)),
                          '{last_redeemed_at}', to_jsonb(%s::text)
                        )
                    WHERE access_id=%s
                      AND download_count=%s
                      AND COALESCE(payload->>'last_redeemed_at', '')=%s
                    RETURNING *
                    """,
                    (
                        repaired_count,
                        repaired_at,
                        repaired_count,
                        repaired_last_redeemed_at,
                        access_id,
                        expected_count,
                        expected_last_redeemed_at,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return access_store._row_record(dict(row)) if row else None

    with access_store._MEMORY_LOCK:
        record = access_store._MEMORY_ACCESS.get(access_id)
        if not record:
            return None
        if int(record.get("download_count") or 0) != expected_count:
            return None
        if str(record.get("last_redeemed_at") or "") != expected_last_redeemed_at:
            return None
        record["download_count"] = repaired_count
        record["last_redeemed_at"] = repaired_last_redeemed_at
        record["updated_at"] = repaired_at
        return deepcopy(record)


def reconcile_orphaned_delivery_consumptions(
    run_or_report_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    actor: str = "delivery_operator",
    grace_seconds: Any = None,
) -> dict[str, Any]:
    """Repair consumed counts that have no verified receipt, using conditional writes."""

    before = approved_delivery_operational_readiness(run_or_report_id, customer_id, project_id, admin_token)
    if before.get("admin_write"):
        return before
    if before.get("critical_over_receipting"):
        return {
            "status": "blocked",
            "error": "Receipt count exceeds access download count; automatic reconciliation is unsafe.",
            "readiness": before,
        }

    grace = _grace_seconds(grace_seconds)
    now = _now()
    repaired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    receipt_result = list_delivery_receipts(
        str(before.get("run_id") or run_or_report_id),
        customer_id,
        project_id,
        admin_token=admin_token,
    )
    receipts = receipt_result.get("receipts") if isinstance(receipt_result.get("receipts"), list) else []
    receipts_by_access: dict[str, list[dict[str, Any]]] = {}
    for item in receipts:
        if not isinstance(item, dict) or not item.get("verified"):
            continue
        receipts_by_access.setdefault(str(item.get("access_id") or ""), []).append(item)

    for mismatch in before.get("repairable_orphaned_consumptions") or []:
        access_id = str(mismatch.get("access_id") or "")
        expected_count = int(mismatch.get("download_count") or 0)
        receipt_rows = receipts_by_access.get(access_id, [])
        repaired_count = len(receipt_rows)
        expected_last = str(mismatch.get("last_redeemed_at") or "")
        last_time = _parse_iso(expected_last)
        if not last_time:
            skipped.append({**mismatch, "reason": "missing_or_invalid_last_redeemed_at"})
            continue
        age_seconds = int((now - last_time).total_seconds())
        if age_seconds < grace:
            skipped.append({**mismatch, "reason": "within_concurrency_grace_window", "age_seconds": age_seconds, "grace_seconds": grace})
            continue
        repaired_last = max((str(item.get("delivered_at") or "") for item in receipt_rows), default="")
        repaired_at = _iso(now)
        updated = _conditional_repair_access(
            access_id,
            expected_count,
            expected_last,
            repaired_count,
            repaired_last,
            repaired_at,
        )
        if not updated:
            skipped.append({**mismatch, "reason": "concurrent_change_detected"})
            continue
        repair = {
            "access_id": access_id,
            "previous_download_count": expected_count,
            "repaired_download_count": repaired_count,
            "previous_last_redeemed_at": expected_last,
            "repaired_last_redeemed_at": repaired_last,
            "repaired_at": repaired_at,
            "actor": str(actor or "delivery_operator")[:160],
        }
        repaired.append(repair)
        STORE.audit(
            "approved_delivery.orphaned_consumption_reconciled",
            repair,
            customer_id=customer_id,
            project_id=project_id,
        )

    after = approved_delivery_operational_readiness(run_or_report_id, customer_id, project_id, admin_token)
    return {
        "status": "reconciled" if repaired else ("no_change" if not before.get("repairable_orphaned_consumptions") else "blocked"),
        "repaired_count": len(repaired),
        "skipped_count": len(skipped),
        "grace_seconds": grace,
        "repaired": repaired,
        "skipped": skipped,
        "readiness_before": before,
        "readiness_after": after,
        "rule": "Only download counts lacking verified receipts and older than the concurrency grace window are conditionally reduced. Receipt over-counts are never auto-repaired.",
    }
