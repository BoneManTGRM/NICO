from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from nico.comprehensive_run_record import (
    _copy_record_for_update,
    _record_hash,
    validate_comprehensive_run_record,
)
from nico.comprehensive_review_work_v1 import LEDGER_SCHEMA

VERSION = "nico.comprehensive_review_work_record.v1"


def apply_review_work_ledger(
    record: dict[str, Any],
    *,
    ledger: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    validation = validate_comprehensive_run_record(record)
    if validation["status"] != "valid":
        raise ValueError("invalid_run_record:" + ",".join(validation["violations"]))
    if str(record.get("status") or "").casefold() != "review_required":
        raise ValueError("review_work_requires_review_required_run")
    candidate = deepcopy(dict(ledger))
    if str(candidate.get("artifact_schema") or "") != LEDGER_SCHEMA:
        raise ValueError("review_work_ledger_schema_invalid")
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        if str(candidate.get(field) or "").strip() != str(identity.get(field) or "").strip():
            raise ValueError(f"review_work_ledger_identity_mismatch:{field}")

    updated = _copy_record_for_update(record)
    updated["review_work_ledger"] = candidate
    updated["review_work_status"] = {
        "artifact_schema": VERSION,
        "audit_event_count": len(candidate.get("audit_events") or []),
        "updated_at": str(candidate.get("updated_at") or ""),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    updated["updated_at"] = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["human_review_required"] = True
    updated["human_review_completed"] = False
    updated["client_delivery_allowed"] = False
    updated["terminal"] = True
    updated["integrity_sha256"] = _record_hash(updated)
    final_validation = validate_comprehensive_run_record(updated)
    if final_validation["status"] != "valid":
        raise ValueError(
            "invalid_review_work_run_record:" + ",".join(final_validation["violations"])
        )
    return updated


__all__ = ["VERSION", "apply_review_work_ledger"]
