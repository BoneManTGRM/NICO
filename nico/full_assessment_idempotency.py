from __future__ import annotations

import hashlib
from typing import Any

FINAL_REVIEW_ACTION = "final_report_approval"


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _digest(namespace: str, *parts: Any) -> str:
    material = "|".join([_normalized(namespace), *(_normalized(part) for part in parts)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def full_run_report_identity(run_id: str, scan_id: str) -> dict[str, str]:
    """Return the durable identity for one run/scanner report package."""

    key = f"full_run_report:{_digest('full_run_report', run_id, scan_id)}"
    return {
        "idempotency_key": key,
        "report_id": f"report_fullrun_{_digest('report_id', run_id, scan_id)}",
        "run_id": str(run_id or ""),
        "scan_id": str(scan_id or ""),
    }


def full_run_approval_identity(run_id: str, report_id: str) -> dict[str, str]:
    """Return the durable identity for one final-review request per report."""

    key = f"full_run_approval:{_digest('full_run_approval', run_id, report_id, FINAL_REVIEW_ACTION)}"
    return {
        "idempotency_key": key,
        "approval_id": f"approval_fullrun_{_digest('approval_id', run_id, report_id, FINAL_REVIEW_ACTION)}",
        "run_id": str(run_id or ""),
        "report_id": str(report_id or ""),
        "requested_action": FINAL_REVIEW_ACTION,
    }


def matching_report(existing: dict[str, Any] | None, *, run_id: str, idempotency_key: str) -> bool:
    if not isinstance(existing, dict):
        return False
    return (
        str(existing.get("run_id") or "") == str(run_id or "")
        and str(existing.get("idempotency_key") or "") == str(idempotency_key or "")
    )


def matching_approval(
    existing: dict[str, Any] | None,
    *,
    run_id: str,
    report_id: str,
    idempotency_key: str,
) -> bool:
    if not isinstance(existing, dict):
        return False
    return (
        str(existing.get("run_id") or "") == str(run_id or "")
        and str(existing.get("report_id") or "") == str(report_id or "")
        and str(existing.get("requested_action") or "") == FINAL_REVIEW_ACTION
        and str(existing.get("idempotency_key") or "") == str(idempotency_key or "")
    )
