from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from typing import Any

from nico.admin_security import require_admin_write
from nico.mid_assessment_approved_pdf import build_mid_approved_report
from nico.mid_assessment_report import generate_mid_draft_report
from nico.mid_assessment_runs import load_mid_assessment_run
from nico.mid_review_by_exception import build_mid_review_packet
from nico.storage import STORE, StorageAdapter, utc_now

MID_APPROVAL_VERSION = "mid-report-approval-v1"
MID_APPROVAL_RECORD_TYPE = "mid_report_approval"
MID_APPROVAL_STATES = {"pending", "needs_more_evidence", "approved", "rejected"}
MID_APPROVAL_TERMINAL_STATES = {"approved", "rejected"}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decode_pdf(report: dict[str, Any]) -> bytes:
    formats = _dict(report.get("formats"))
    try:
        pdf = base64.b64decode(str(formats.get("pdf") or ""), validate=True)
    except Exception:
        return b""
    return pdf if pdf.startswith(b"%PDF") else b""


def _approval_identity(report: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    exception_ids = sorted(
        str(item.get("item_id") or "")
        for item in _list(packet.get("exceptions"))
        if isinstance(item, dict) and str(item.get("item_id") or "")
    )
    return {
        "approval_version": MID_APPROVAL_VERSION,
        "run_id": report.get("run_id") or "",
        "customer_id": report.get("customer_id") or "default_customer",
        "project_id": report.get("project_id") or "default_project",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "draft_report_id": report.get("report_id") or "",
        "draft_report_version": report.get("report_version") or "",
        "draft_pdf_sha256": report.get("pdf_sha256") or "",
        "source_identity_sha256": report.get("source_identity_sha256") or "",
        "review_packet_id": packet.get("review_packet_id") or "",
        "review_packet_sha256": packet.get("review_packet_sha256") or "",
        "exception_item_ids": exception_ids,
        "unsupported_claims_permitted": int(report.get("unsupported_claims_permitted") or 0),
    }


def _approval_id(identity: dict[str, Any]) -> str:
    return f"mid_approval_{_canonical_hash(identity)[:24]}"


def _public_approval(value: Any, *, include_validation: bool = True, store: StorageAdapter | None = None) -> dict[str, Any]:
    approval = value if isinstance(value, dict) else {}
    if not approval:
        return {}
    decision = _dict(approval.get("review_decision"))
    approved_report = _dict(approval.get("approved_report"))
    result = {
        "approval_id": approval.get("approval_id") or "",
        "approval_version": approval.get("approval_version") or "",
        "status": approval.get("status") or "unknown",
        "requested_action": approval.get("requested_action") or "mid_report_approval",
        "run_id": approval.get("run_id") or "",
        "customer_id": approval.get("customer_id") or "default_customer",
        "project_id": approval.get("project_id") or "default_project",
        "repository": approval.get("repository") or "",
        "snapshot_id": approval.get("snapshot_id") or "",
        "snapshot_commit_sha": approval.get("snapshot_commit_sha") or "",
        "draft_report_id": approval.get("draft_report_id") or "",
        "draft_pdf_sha256": approval.get("draft_pdf_sha256") or "",
        "source_identity_sha256": approval.get("source_identity_sha256") or "",
        "review_packet_id": approval.get("review_packet_id") or "",
        "review_packet_sha256": approval.get("review_packet_sha256") or "",
        "exception_item_ids": list(approval.get("exception_item_ids") or []),
        "exception_item_count": len(_list(approval.get("exception_item_ids"))),
        "created_at": approval.get("created_at") or "",
        "updated_at": approval.get("updated_at") or "",
        "review_decision": {
            "state": decision.get("state") or "",
            "actor": decision.get("actor") or "",
            "note": decision.get("note") or "",
            "decided_at": decision.get("decided_at") or "",
            "reviewed_item_ids": list(decision.get("reviewed_item_ids") or []),
            "reviewed_item_count": len(_list(decision.get("reviewed_item_ids"))),
            "approved_report_id": decision.get("approved_report_id") or "",
            "delivery_eligible": bool(decision.get("delivery_eligible")),
            "client_delivery_allowed": bool(decision.get("client_delivery_allowed")),
        },
        "approved_report": {
            "status": approved_report.get("status") or "",
            "report_id": approved_report.get("report_id") or "",
            "report_version": approved_report.get("report_version") or "",
            "pdf_sha256": approved_report.get("pdf_sha256") or "",
            "pdf_filename": approved_report.get("pdf_filename") or "",
            "approval_identity_sha256": approved_report.get("approval_identity_sha256") or "",
            "delivery_eligible": bool(approved_report.get("delivery_eligible")),
            "client_delivery_allowed": bool(approved_report.get("client_delivery_allowed")),
        },
        "human_approval_required": approval.get("status") not in MID_APPROVAL_TERMINAL_STATES,
        "approved": approval.get("status") == "approved",
        "delivery_eligible": approval.get("status") == "approved" and bool(approved_report.get("delivery_eligible")),
        "client_delivery_allowed": False,
        "rule": "Mid approval is bound to the exact draft, snapshot, truth identity, and review packet. Approval creates a separate approved PDF but does not create or authorize a client delivery link.",
    }
    if include_validation:
        result["validation"] = validate_mid_approval(approval, store=store)
    return result


def request_mid_approval(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to request Mid approval.", "admin_write": admin}
    active = _store(store)
    report = generate_mid_draft_report(run_id, customer_id, project_id, admin_token=admin_token, store=active)
    if report.get("status") == "not_found":
        return report
    if report.get("status") != "complete":
        return {"status": "blocked", "error": str(report.get("error") or "A valid Mid draft is required before approval.")}
    packet = build_mid_review_packet(run_id, customer_id, project_id, admin_token=admin_token, store=active)
    if packet.get("status") != "ready_for_review":
        return {"status": "blocked", "error": "A current Mid review packet is required before approval."}
    identity = _approval_identity(report, packet)
    if identity["unsupported_claims_permitted"] != 0:
        return {"status": "blocked", "error": "Mid approval cannot be requested while unsupported claims are permitted."}
    approval_id = _approval_id(identity)
    existing = active.get("approvals", approval_id)
    if isinstance(existing, dict) and existing.get("record_type") == MID_APPROVAL_RECORD_TYPE:
        return {"status": "requested", "idempotent_reuse": True, "approval": _public_approval(existing, store=active)}
    now = utc_now()
    record = {
        "record_type": MID_APPROVAL_RECORD_TYPE,
        "approval_id": approval_id,
        "approval_version": MID_APPROVAL_VERSION,
        "requested_action": "mid_report_approval",
        "status": "pending",
        "run_id": identity["run_id"],
        "customer_id": identity["customer_id"],
        "project_id": identity["project_id"],
        "repository": identity["repository"],
        "snapshot_id": identity["snapshot_id"],
        "snapshot_commit_sha": identity["snapshot_commit_sha"],
        "draft_report_id": identity["draft_report_id"],
        "draft_report_version": identity["draft_report_version"],
        "draft_pdf_sha256": identity["draft_pdf_sha256"],
        "source_identity_sha256": identity["source_identity_sha256"],
        "review_packet_id": identity["review_packet_id"],
        "review_packet_sha256": identity["review_packet_sha256"],
        "exception_item_ids": identity["exception_item_ids"],
        "approval_identity": identity,
        "approval_identity_sha256": _canonical_hash(identity),
        "review_decision": {},
        "approved_report": {},
        "created_at": now,
        "updated_at": now,
    }
    active.put("approvals", approval_id, record)
    run = load_mid_assessment_run(run_id, store=active)
    if run:
        updated = deepcopy(run)
        updated["approval_id"] = approval_id
        updated["updated_at"] = utc_now()
        active.put("assessment_runs", run_id, updated)
    active.audit(
        "mid.approval_requested",
        {
            "approval_id": approval_id,
            "approval_identity_sha256": record["approval_identity_sha256"],
            "run_id": run_id,
            "draft_report_id": identity["draft_report_id"],
            "draft_pdf_sha256": identity["draft_pdf_sha256"],
            "review_packet_id": identity["review_packet_id"],
            "review_packet_sha256": identity["review_packet_sha256"],
            "exception_item_count": len(identity["exception_item_ids"]),
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return {"status": "requested", "idempotent_reuse": False, "approval": _public_approval(record, store=active)}


def validate_mid_approval(value: Any, store: StorageAdapter | None = None) -> dict[str, Any]:
    approval = value if isinstance(value, dict) else {}
    active = _store(store)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, message: str, evidence: Any = None) -> None:
        item = {"id": check_id, "passed": bool(passed), "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        checks.append(item)

    check("approval_exists", bool(approval), "The Mid approval record exists.")
    check("record_type", approval.get("record_type") == MID_APPROVAL_RECORD_TYPE, "The record is a Mid report approval.")
    check("approval_version", approval.get("approval_version") == MID_APPROVAL_VERSION, "The approval uses the supported version.")
    run_id = str(approval.get("run_id") or "")
    customer_id = str(approval.get("customer_id") or "default_customer")
    project_id = str(approval.get("project_id") or "default_project")
    run = load_mid_assessment_run(run_id, store=active) if run_id else None
    check("mid_run", bool(run), "The exact Mid run still exists.")
    if run:
        check("scope", run.get("customer_id") == customer_id and run.get("project_id") == project_id, "The approval scope matches the Mid run.")
        check("snapshot", run.get("snapshot_id") == approval.get("snapshot_id") and run.get("snapshot_commit_sha") == approval.get("snapshot_commit_sha"), "The Mid snapshot identity is unchanged.")
    report = generate_mid_draft_report(run_id, customer_id, project_id, admin_token=None if False else "", store=active)
    # The internal validation path cannot rely on an admin credential. Load the
    # current report deterministically from the approval binding and separately
    # recompute current truth/review identities below.
    report = active.get("reports", str(approval.get("draft_report_id") or "")) or {}
    pdf = _decode_pdf(report)
    check("draft_report", report.get("record_type") == "mid_assessment_report" and report.get("status") == "complete", "The exact Mid draft report exists.")
    check("draft_pdf", bool(pdf) and hashlib.sha256(pdf).hexdigest() == str(approval.get("draft_pdf_sha256") or ""), "The draft PDF matches the approval-bound SHA-256.")
    check("report_identity", report.get("source_identity_sha256") == approval.get("source_identity_sha256"), "The draft source identity is unchanged.")
    check("report_snapshot", report.get("snapshot_id") == approval.get("snapshot_id") and report.get("snapshot_commit_sha") == approval.get("snapshot_commit_sha"), "The draft is bound to the approved snapshot.")
    check("unsupported_claims", int(report.get("unsupported_claims_permitted") or 0) == 0, "Unsupported claims permitted remains zero.")
    packet = build_mid_review_packet(run_id, customer_id, project_id, admin_token="", store=active)
    # build_mid_review_packet is admin-guarded; use the stored packet evidence
    # and recompute the truth-derived identity directly through the report's
    # current review-packet binding.
    packet = _dict(_dict(active.get("evidence_items", str(approval.get("review_packet_id") or ""))).get("evidence"))
    check("review_packet", packet.get("status") == "ready_for_review", "The exact review-by-exception packet exists.")
    check("review_packet_hash", packet.get("review_packet_sha256") == approval.get("review_packet_sha256"), "The review packet SHA-256 matches the approval binding.")
    current_exception_ids = sorted(
        str(item.get("item_id") or "")
        for item in _list(packet.get("exceptions"))
        if isinstance(item, dict) and str(item.get("item_id") or "")
    )
    expected_exception_ids = sorted(str(item) for item in _list(approval.get("exception_item_ids")) if str(item))
    check("exception_items", current_exception_ids == expected_exception_ids, "The exception item set is unchanged.", current_exception_ids)
    identity = _dict(approval.get("approval_identity"))
    check("approval_identity", bool(identity) and _canonical_hash(identity) == approval.get("approval_identity_sha256"), "The approval identity SHA-256 is valid.")
    blockers = [item["message"] for item in checks if not item["passed"]]
    return {
        "status": "ready" if not blockers else "blocked",
        "ready_for_approval": not blockers,
        "checks": checks,
        "blockers": blockers,
        "exception_item_ids": expected_exception_ids,
        "exception_item_count": len(expected_exception_ids),
        "rule": "Approval is allowed only while the exact Mid run, snapshot, draft PDF, source identity, review packet, and exception item set remain unchanged.",
    }


def transition_mid_approval(
    approval_id: str,
    state: str,
    actor: str,
    note: str = "",
    reviewed_item_ids: list[str] | None = None,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to decide Mid approval.", "admin_write": admin}
    active = _store(store)
    approval = active.get("approvals", str(approval_id or ""))
    if not isinstance(approval, dict) or approval.get("record_type") != MID_APPROVAL_RECORD_TYPE:
        return {"status": "not_found", "error": "Mid approval not found."}
    requested_state = str(state or "").strip().lower()
    if requested_state not in {"approved", "rejected", "needs_more_evidence"}:
        return {"status": "blocked", "error": "Unsupported Mid approval state."}
    reviewer = " ".join(str(actor or "").split())[:160]
    decision_note = str(note or "").strip()[:4000]
    reviewed = sorted(set(str(item) for item in (reviewed_item_ids or []) if str(item)))
    if len(reviewer) < 2:
        return {"status": "blocked", "error": "Reviewer identity is required."}
    if requested_state == "approved" and len(decision_note) < 10:
        return {"status": "blocked", "error": "Approval requires a substantive reviewer note."}
    if requested_state in {"rejected", "needs_more_evidence"} and len(decision_note) < 5:
        return {"status": "blocked", "error": "A reviewer note is required for this decision."}
    current_state = str(approval.get("status") or "pending")
    existing_decision = _dict(approval.get("review_decision"))
    if current_state in MID_APPROVAL_TERMINAL_STATES:
        if current_state == requested_state:
            return {"status": current_state, "idempotent_reuse": True, "approval": _public_approval(approval, store=active)}
        return {"status": "blocked", "error": "A terminal Mid approval decision cannot be reversed."}

    validation = validate_mid_approval(approval, store=active)
    if requested_state == "approved" and not validation.get("ready_for_approval"):
        return {"status": "blocked", "error": "The Mid approval source no longer passes exact identity validation.", "validation": validation}
    expected_items = sorted(str(item) for item in _list(approval.get("exception_item_ids")) if str(item))
    if requested_state == "approved" and reviewed != expected_items:
        missing = sorted(set(expected_items) - set(reviewed))
        extra = sorted(set(reviewed) - set(expected_items))
        return {
            "status": "blocked",
            "error": "Every current review exception must be explicitly acknowledged before approval.",
            "missing_reviewed_item_ids": missing,
            "unexpected_reviewed_item_ids": extra,
        }

    decided_at = utc_now()
    updated = deepcopy(approval)
    updated["status"] = requested_state
    updated["updated_at"] = decided_at
    updated["review_decision"] = {
        "state": requested_state,
        "actor": reviewer,
        "note": decision_note,
        "decided_at": decided_at,
        "reviewed_item_ids": reviewed,
        "delivery_eligible": False,
        "client_delivery_allowed": False,
    }

    approved_report: dict[str, Any] = {}
    if requested_state == "approved":
        draft = active.get("reports", str(approval.get("draft_report_id") or "")) or {}
        candidate = build_mid_approved_report(draft, updated)
        if candidate.get("status") != "complete":
            return {"status": "blocked", "error": str(candidate.get("error") or "Approved Mid PDF generation failed.")}
        existing_approved = active.get("reports", str(candidate.get("report_id") or ""))
        if isinstance(existing_approved, dict) and existing_approved.get("pdf_sha256") == candidate.get("pdf_sha256"):
            approved_report = existing_approved
        else:
            approved_report = candidate
            active.put("reports", str(candidate["report_id"]), candidate)
        updated["approved_report"] = {
            "status": approved_report.get("status") or "",
            "report_id": approved_report.get("report_id") or "",
            "report_version": approved_report.get("report_version") or "",
            "pdf_sha256": approved_report.get("pdf_sha256") or "",
            "pdf_filename": approved_report.get("pdf_filename") or "",
            "approval_identity_sha256": approved_report.get("approval_identity_sha256") or "",
            "delivery_eligible": True,
            "client_delivery_allowed": False,
        }
        updated["review_decision"].update(
            {
                "approved_report_id": approved_report.get("report_id") or "",
                "delivery_eligible": True,
                "client_delivery_allowed": False,
            }
        )

    active.put("approvals", approval_id, updated)
    run = load_mid_assessment_run(str(approval.get("run_id") or ""), store=active)
    if run:
        updated_run = deepcopy(run)
        updated_run["approval_id"] = approval_id
        if approved_report:
            updated_run["approved_report_id"] = approved_report.get("report_id") or ""
        updated_run["updated_at"] = utc_now()
        active.put("assessment_runs", str(approval.get("run_id") or ""), updated_run)
    draft = active.get("reports", str(approval.get("draft_report_id") or ""))
    if isinstance(draft, dict):
        updated_draft = deepcopy(draft)
        updated_draft["approval_id"] = approval_id
        updated_draft["approval_status"] = requested_state
        if approved_report:
            updated_draft["approved_report_id"] = approved_report.get("report_id") or ""
        active.put("reports", str(approval.get("draft_report_id") or ""), updated_draft)
    active.audit(
        "mid.approval_decided",
        {
            "approval_id": approval_id,
            "state": requested_state,
            "actor": reviewer,
            "run_id": approval.get("run_id") or "",
            "draft_report_id": approval.get("draft_report_id") or "",
            "draft_pdf_sha256": approval.get("draft_pdf_sha256") or "",
            "review_packet_id": approval.get("review_packet_id") or "",
            "review_packet_sha256": approval.get("review_packet_sha256") or "",
            "reviewed_item_count": len(reviewed),
            "approved_report_id": approved_report.get("report_id") or "",
            "approved_pdf_sha256": approved_report.get("pdf_sha256") or "",
            "delivery_eligible": bool(approved_report),
            "client_delivery_allowed": False,
        },
        customer_id=str(approval.get("customer_id") or "default_customer"),
        project_id=str(approval.get("project_id") or "default_project"),
    )
    return {"status": requested_state, "idempotent_reuse": False, "approval": _public_approval(updated, store=active)}


def mid_approval_status(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to inspect Mid approval.", "admin_write": admin}
    active = _store(store)
    run = load_mid_assessment_run(str(run_id or ""), store=active)
    if not run or run.get("customer_id") != customer_id or run.get("project_id") != project_id:
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    approval_id = str(run.get("approval_id") or "")
    approval = active.get("approvals", approval_id) if approval_id else None
    if not isinstance(approval, dict) or approval.get("record_type") != MID_APPROVAL_RECORD_TYPE:
        return {"status": "not_requested", "run_id": run_id, "approval": {}}
    return {"status": str(approval.get("status") or "pending"), "run_id": run_id, "approval": _public_approval(approval, store=active)}


def get_mid_approved_report(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to access the approved Mid report.", "admin_write": admin}
    active = _store(store)
    run = load_mid_assessment_run(str(run_id or ""), store=active)
    if not run or run.get("customer_id") != customer_id or run.get("project_id") != project_id:
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    approved_report_id = str(run.get("approved_report_id") or "")
    report = active.get("reports", approved_report_id) if approved_report_id else None
    if not isinstance(report, dict) or report.get("record_type") != "mid_approved_report":
        return {"status": "not_found", "error": "Approved Mid report not found."}
    return report
