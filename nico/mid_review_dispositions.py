from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from nico.admin_security import require_admin_write
from nico.storage import STORE, StorageAdapter, utc_now

REVIEW_DISPOSITION_VERSION = "mid-review-disposition-v1"
REVIEW_DISPOSITION_DECISIONS = {
    "accepted",
    "accepted_inference_only",
    "needs_more_evidence",
    "rejected",
}
REVIEW_DISPOSITION_APPROVAL_STATES = {"accepted", "accepted_inference_only"}
_TERMINAL_APPROVAL_STATES = {"approved", "rejected"}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _packet(active: StorageAdapter, approval: dict[str, Any]) -> dict[str, Any]:
    packet_id = str(approval.get("review_packet_id") or "")
    item = active.get("evidence_items", packet_id) if packet_id else None
    return _dict(_dict(item).get("evidence"))


def _packet_items(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("item_id") or ""): item
        for item in _list(packet.get("exceptions"))
        if isinstance(item, dict) and str(item.get("item_id") or "")
    }


def _clean_actor(value: str) -> str:
    return " ".join(str(value or "").split())[:160]


def _clean_note(value: str) -> str:
    return str(value or "").strip()[:4000]


def _public_disposition(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": record.get("version") or REVIEW_DISPOSITION_VERSION,
        "item_id": record.get("item_id") or "",
        "decision": record.get("decision") or "pending",
        "actor": record.get("actor") or "",
        "note": record.get("note") or "",
        "decided_at": record.get("decided_at") or "",
        "item_sha256": record.get("item_sha256") or "",
        "disposition_sha256": record.get("disposition_sha256") or "",
        "review_packet_id": record.get("review_packet_id") or "",
        "review_packet_sha256": record.get("review_packet_sha256") or "",
        "truth_sha256": record.get("truth_sha256") or "",
        "snapshot_commit_sha": record.get("snapshot_commit_sha") or "",
    }


def review_disposition_summary(approval: dict[str, Any], store: StorageAdapter | None = None) -> dict[str, Any]:
    active = _store(store)
    packet = _packet(active, approval)
    packet_items = _packet_items(packet)
    expected = sorted(str(item) for item in _list(approval.get("exception_item_ids")) if str(item))
    stored = _dict(approval.get("review_item_dispositions"))
    items: list[dict[str, Any]] = []
    accepted_ids: list[str] = []
    pending_ids: list[str] = []
    blocking_ids: list[str] = []
    stale_ids: list[str] = []

    packet_hash_matches = bool(packet) and packet.get("review_packet_sha256") == approval.get("review_packet_sha256")
    for item_id in expected:
        source_item = _dict(packet_items.get(item_id))
        source_hash = _canonical_hash(source_item) if source_item else ""
        record = _dict(stored.get(item_id))
        record_valid = bool(record) and record.get("item_sha256") == source_hash and record.get("review_packet_sha256") == approval.get("review_packet_sha256")
        decision = str(record.get("decision") or "pending") if record_valid else "pending"
        if record and not record_valid:
            stale_ids.append(item_id)
        if decision in REVIEW_DISPOSITION_APPROVAL_STATES:
            accepted_ids.append(item_id)
        elif decision in {"needs_more_evidence", "rejected"}:
            blocking_ids.append(item_id)
        else:
            pending_ids.append(item_id)
        items.append(
            {
                "item_id": item_id,
                "title": source_item.get("title") or item_id,
                "category": source_item.get("category") or "unknown",
                "section_id": source_item.get("section_id") or "",
                "severity": source_item.get("severity") or "medium",
                "reason": source_item.get("reason") or "",
                "evidence": list(source_item.get("evidence") or []),
                "blockers": list(source_item.get("blockers") or []),
                "inference_based": bool(source_item.get("inference_based")),
                "score_change_material": bool(source_item.get("score_change_material")),
                "decision_status": decision,
                "disposition": _public_disposition(record) if record_valid else {},
            }
        )

    digest_payload = [
        {
            "item_id": item["item_id"],
            "decision": item["decision_status"],
            "disposition_sha256": _dict(item.get("disposition")).get("disposition_sha256") or "",
        }
        for item in items
    ]
    ready = packet_hash_matches and not pending_ids and not blocking_ids and not stale_ids
    return {
        "version": REVIEW_DISPOSITION_VERSION,
        "status": "ready" if ready else "review_required",
        "approval_ready": ready,
        "review_packet_valid": packet_hash_matches,
        "expected_item_count": len(expected),
        "accepted_item_count": len(accepted_ids),
        "pending_item_count": len(pending_ids),
        "blocking_item_count": len(blocking_ids),
        "stale_item_count": len(stale_ids),
        "accepted_item_ids": accepted_ids,
        "pending_item_ids": pending_ids,
        "blocking_item_ids": blocking_ids,
        "stale_item_ids": stale_ids,
        "items": items,
        "disposition_set_sha256": _canonical_hash(digest_payload),
        "rule": "Each current review exception should receive an item-level disposition. Needs-more-evidence, rejected, stale, or pending items block the structured approval path.",
    }


def submit_mid_review_disposition(
    approval_id: str,
    item_id: str,
    decision: str,
    actor: str,
    note: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to review Mid exceptions.", "admin_write": admin}
    active = _store(store)
    approval = active.get("approvals", str(approval_id or ""))
    if not isinstance(approval, dict) or approval.get("record_type") != "mid_report_approval":
        return {"status": "not_found", "error": "Mid approval not found."}
    if str(approval.get("status") or "pending") in _TERMINAL_APPROVAL_STATES:
        return {"status": "blocked", "error": "Review dispositions cannot change after a terminal approval decision."}

    requested = str(decision or "").strip().lower()
    if requested not in REVIEW_DISPOSITION_DECISIONS:
        return {"status": "blocked", "error": "Unsupported Mid review disposition."}
    reviewer = _clean_actor(actor)
    decision_note = _clean_note(note)
    if len(reviewer) < 2:
        return {"status": "blocked", "error": "Reviewer identity is required."}
    minimum_note = 12 if requested in {"needs_more_evidence", "rejected"} else 8
    if len(decision_note) < minimum_note:
        return {"status": "blocked", "error": "A substantive item-level reviewer note is required."}

    packet = _packet(active, approval)
    if not packet or packet.get("review_packet_sha256") != approval.get("review_packet_sha256"):
        return {"status": "blocked", "error": "The approval-bound review packet is missing or stale."}
    source_item = _dict(_packet_items(packet).get(str(item_id or "")))
    if not source_item or str(item_id) not in {str(value) for value in _list(approval.get("exception_item_ids"))}:
        return {"status": "not_found", "error": "Mid review exception not found in the current approval set."}
    if requested == "accepted_inference_only":
        if not bool(source_item.get("inference_based")):
            return {"status": "blocked", "error": "Inference-only acceptance is allowed only for an inference-based exception."}
        if bool(source_item.get("score_change_material")):
            return {"status": "blocked", "error": "A score-changing inference cannot be accepted as inference-only. Request evidence or reject the item."}

    decided_at = utc_now()
    identity = {
        "version": REVIEW_DISPOSITION_VERSION,
        "approval_id": approval.get("approval_id") or "",
        "run_id": approval.get("run_id") or "",
        "customer_id": approval.get("customer_id") or "default_customer",
        "project_id": approval.get("project_id") or "default_project",
        "snapshot_id": approval.get("snapshot_id") or "",
        "snapshot_commit_sha": approval.get("snapshot_commit_sha") or "",
        "truth_sha256": approval.get("truth_sha256") or "",
        "review_packet_id": approval.get("review_packet_id") or "",
        "review_packet_sha256": approval.get("review_packet_sha256") or "",
        "item_id": str(item_id),
        "item_sha256": _canonical_hash(source_item),
        "decision": requested,
        "actor": reviewer,
        "note_sha256": hashlib.sha256(decision_note.encode("utf-8")).hexdigest(),
        "decided_at": decided_at,
    }
    record = {
        **identity,
        "note": decision_note,
        "disposition_sha256": _canonical_hash(identity),
    }
    updated = deepcopy(approval)
    dispositions = _dict(updated.get("review_item_dispositions"))
    dispositions[str(item_id)] = record
    updated["review_item_dispositions"] = dispositions
    updated["review_item_disposition_sha256"] = _canonical_hash(
        {key: _dict(value).get("disposition_sha256") or "" for key, value in sorted(dispositions.items())}
    )
    updated["updated_at"] = decided_at
    active.put("approvals", str(approval_id), updated)
    summary = review_disposition_summary(updated, store=active)
    active.audit(
        "mid.review_item_disposition_recorded",
        {
            "approval_id": approval.get("approval_id") or "",
            "run_id": approval.get("run_id") or "",
            "item_id": str(item_id),
            "decision": requested,
            "actor": reviewer,
            "disposition_sha256": record["disposition_sha256"],
            "disposition_set_sha256": summary["disposition_set_sha256"],
            "approval_ready": summary["approval_ready"],
        },
        customer_id=str(approval.get("customer_id") or "default_customer"),
        project_id=str(approval.get("project_id") or "default_project"),
    )
    return {
        "status": "recorded",
        "disposition": _public_disposition(record),
        "review_dispositions": summary,
    }


def get_mid_review_dispositions(
    approval_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to inspect Mid review dispositions.", "admin_write": admin}
    active = _store(store)
    approval = active.get("approvals", str(approval_id or ""))
    if not isinstance(approval, dict) or approval.get("record_type") != "mid_report_approval":
        return {"status": "not_found", "error": "Mid approval not found."}
    return {
        "status": "ready",
        "approval_id": approval.get("approval_id") or "",
        "review_dispositions": review_disposition_summary(approval, store=active),
    }


__all__ = [
    "REVIEW_DISPOSITION_VERSION",
    "REVIEW_DISPOSITION_DECISIONS",
    "REVIEW_DISPOSITION_APPROVAL_STATES",
    "review_disposition_summary",
    "submit_mid_review_disposition",
    "get_mid_review_dispositions",
]
