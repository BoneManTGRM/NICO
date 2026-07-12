from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from copy import deepcopy
from typing import Any, Callable

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

import nico.mid_approval_api as approval_api
import nico.mid_assessment_approval as approval_service
import nico.mid_assessment_approved_pdf as approved_pdf_service
import nico.mid_delivery_access as delivery_service
import nico.mid_review_dispositions as disposition_service
from nico.storage import STORE, StorageAdapter

MID_APPROVAL_ENFORCED_VERSION = "mid-report-approval-v3"
MID_APPROVAL_LEGACY_VERSIONS = {"mid-report-approval-v2"}
MID_REVIEW_ENFORCEMENT_VERSION = "mid-review-enforcement-v1"

_INSTALLED = False
_ORIGINALS: dict[str, Callable[..., Any]] = {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decode_pdf(report: dict[str, Any]) -> bytes:
    try:
        pdf = base64.b64decode(str(_dict(report.get("formats")).get("pdf") or ""), validate=True)
    except Exception:
        return b""
    return pdf if pdf.startswith(b"%PDF") else b""


def _active_store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _is_enforced(approval: dict[str, Any]) -> bool:
    return str(approval.get("approval_version") or "") == MID_APPROVAL_ENFORCED_VERSION


def _disposition_identity(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"note", "disposition_sha256"}}


def _binding_valid(record: dict[str, Any], approval: dict[str, Any]) -> bool:
    if not record:
        return False
    identity = _disposition_identity(record)
    note = str(record.get("note") or "")
    return bool(
        record.get("approval_id") == approval.get("approval_id")
        and record.get("run_id") == approval.get("run_id")
        and record.get("customer_id") == approval.get("customer_id")
        and record.get("project_id") == approval.get("project_id")
        and record.get("snapshot_id") == approval.get("snapshot_id")
        and record.get("snapshot_commit_sha") == approval.get("snapshot_commit_sha")
        and record.get("truth_sha256") == approval.get("truth_sha256")
        and record.get("review_packet_id") == approval.get("review_packet_id")
        and record.get("review_packet_sha256") == approval.get("review_packet_sha256")
        and hashlib.sha256(note.encode("utf-8")).hexdigest() == record.get("note_sha256")
        and _canonical_hash(identity) == record.get("disposition_sha256")
    )


def _strict_review_disposition_summary(approval: dict[str, Any], store: StorageAdapter | None = None) -> dict[str, Any]:
    original = _ORIGINALS["review_disposition_summary"]
    summary = deepcopy(original(approval, store=store))
    if not _is_enforced(approval):
        return summary

    stored = _dict(approval.get("review_item_dispositions"))
    accepted: list[str] = []
    pending: list[str] = []
    blocking: list[str] = []
    stale: list[str] = []
    digest_payload: list[dict[str, str]] = []

    for item in _list(summary.get("items")):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or "")
        record = _dict(stored.get(item_id))
        valid = _binding_valid(record, approval) and bool(item.get("disposition"))
        decision = str(record.get("decision") or "pending") if valid else "pending"
        if record and not valid:
            stale.append(item_id)
        if decision in disposition_service.REVIEW_DISPOSITION_APPROVAL_STATES:
            accepted.append(item_id)
        elif decision in {"needs_more_evidence", "rejected"}:
            blocking.append(item_id)
        else:
            pending.append(item_id)
        item["decision_status"] = decision
        item["disposition"] = disposition_service._public_disposition(record) if valid else {}
        item["binding_valid"] = valid
        digest_payload.append(
            {
                "item_id": item_id,
                "decision": decision,
                "disposition_sha256": str(record.get("disposition_sha256") or "") if valid else "",
            }
        )

    ready = bool(summary.get("review_packet_valid")) and not pending and not blocking and not stale
    summary.update(
        {
            "version": disposition_service.REVIEW_DISPOSITION_VERSION,
            "enforcement_version": MID_REVIEW_ENFORCEMENT_VERSION,
            "status": "ready" if ready else "review_required",
            "approval_ready": ready,
            "accepted_item_count": len(accepted),
            "pending_item_count": len(pending),
            "blocking_item_count": len(blocking),
            "stale_item_count": len(stale),
            "accepted_item_ids": accepted,
            "pending_item_ids": pending,
            "blocking_item_ids": blocking,
            "stale_item_ids": stale,
            "disposition_set_sha256": _canonical_hash(digest_payload),
            "rule": "Every current exception must have a valid item-level disposition bound to the exact approval, run, snapshot, truth model, review packet, item content, reviewer note, and decision.",
        }
    )
    return summary


def _recompute_validation(result: dict[str, Any]) -> dict[str, Any]:
    checks = [item for item in _list(result.get("checks")) if isinstance(item, dict)]
    blockers = [str(item.get("message") or item.get("id") or "Validation failed.") for item in checks if not item.get("passed")]
    result["checks"] = checks
    result["blockers"] = blockers
    result["status"] = "ready" if not blockers else "blocked"
    result["ready_for_approval"] = not blockers
    return result


def _add_check(result: dict[str, Any], check_id: str, passed: bool, message: str, evidence: Any = None) -> None:
    check = {"id": check_id, "passed": bool(passed), "message": message}
    if evidence is not None:
        check["evidence"] = evidence
    result.setdefault("checks", []).append(check)


def _enforced_validate_mid_approval(value: Any, store: StorageAdapter | None = None) -> dict[str, Any]:
    approval = value if isinstance(value, dict) else {}
    result = deepcopy(_ORIGINALS["validate_mid_approval"](approval, store=store))
    version = str(approval.get("approval_version") or "")

    if version in MID_APPROVAL_LEGACY_VERSIONS:
        for check in _list(result.get("checks")):
            if isinstance(check, dict) and check.get("id") == "approval_version":
                check["passed"] = True
                check["message"] = "The legacy Mid approval version remains supported for retained records."
        result["legacy_approval"] = True
        return _recompute_validation(result)

    if version != MID_APPROVAL_ENFORCED_VERSION:
        return result

    summary = _strict_review_disposition_summary(approval, store=store)
    identity = _dict(approval.get("approval_identity"))
    disposition_hash = str(summary.get("disposition_set_sha256") or "")
    finalized_hash = str(approval.get("review_disposition_set_sha256") or "")
    finalized = bool(finalized_hash)
    expected_phase = "approved" if finalized else "requested"
    expected_count = int(summary.get("expected_item_count") or 0) if finalized else 0
    expected_hash = disposition_hash if finalized else ""

    _add_check(
        result,
        "review_disposition_policy",
        approval.get("review_disposition_required") is True
        and approval.get("review_disposition_policy_version") == MID_REVIEW_ENFORCEMENT_VERSION,
        "The approval requires the current item-level review-disposition policy.",
    )
    _add_check(
        result,
        "review_dispositions_ready",
        bool(summary.get("approval_ready")),
        "Every current review exception has an approval-compatible, exact-state disposition.",
        {
            "accepted": summary.get("accepted_item_count"),
            "pending": summary.get("pending_item_count"),
            "blocking": summary.get("blocking_item_count"),
            "stale": summary.get("stale_item_count"),
        },
    )
    _add_check(
        result,
        "review_disposition_identity",
        identity.get("approval_phase") == expected_phase
        and identity.get("review_disposition_required") is True
        and identity.get("review_disposition_policy_version") == MID_REVIEW_ENFORCEMENT_VERSION
        and str(identity.get("review_disposition_set_sha256") or "") == expected_hash
        and int(identity.get("review_disposition_count") or 0) == expected_count,
        "The approval identity is bound to the current review-disposition phase and set hash.",
        {"phase": expected_phase, "disposition_set_sha256": expected_hash, "count": expected_count},
    )
    if finalized:
        decision = _dict(approval.get("review_decision"))
        report = _dict(_dict(approval.get("approved_report")))
        _add_check(
            result,
            "review_disposition_final_hash",
            finalized_hash == disposition_hash
            and decision.get("review_disposition_set_sha256") == disposition_hash
            and report.get("review_disposition_set_sha256") == disposition_hash,
            "The finalized approval, decision, and approved artifact reference the unchanged disposition-set hash.",
            disposition_hash,
        )

    result["review_dispositions"] = summary
    result["review_disposition_required"] = True
    return _recompute_validation(result)


def _request_identity(approval: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(_dict(approval.get("approval_identity")))
    identity.update(
        {
            "approval_version": MID_APPROVAL_ENFORCED_VERSION,
            "approval_phase": "requested",
            "review_disposition_required": True,
            "review_disposition_policy_version": MID_REVIEW_ENFORCEMENT_VERSION,
            "review_disposition_set_sha256": "",
            "review_disposition_count": 0,
        }
    )
    return identity


def _enforced_request_mid_approval(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _active_store(store)
    result = _ORIGINALS["request_mid_approval"](
        run_id,
        customer_id,
        project_id,
        admin_token=admin_token,
        store=active,
    )
    approval = _dict(_dict(result).get("approval"))
    approval_id = str(approval.get("approval_id") or "")
    stored = active.get("approvals", approval_id) if approval_id else None
    if not isinstance(stored, dict) or str(stored.get("approval_version") or "") != MID_APPROVAL_ENFORCED_VERSION:
        return result

    updated = deepcopy(stored)
    updated["review_disposition_required"] = True
    updated["review_disposition_policy_version"] = MID_REVIEW_ENFORCEMENT_VERSION
    updated.setdefault("review_item_dispositions", {})
    updated.setdefault("review_item_disposition_sha256", "")
    updated.setdefault("review_disposition_set_sha256", "")
    updated.setdefault("review_disposition_count", 0)
    updated["approval_identity"] = _request_identity(updated)
    updated["approval_identity_sha256"] = _canonical_hash(updated["approval_identity"])
    active.put("approvals", approval_id, updated)
    return {
        **result,
        "approval": _enforced_public_approval(updated, store=active),
    }


def _final_identity(approval: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(_dict(approval.get("approval_identity")))
    identity.update(
        {
            "approval_version": MID_APPROVAL_ENFORCED_VERSION,
            "approval_phase": "approved",
            "review_disposition_required": True,
            "review_disposition_policy_version": MID_REVIEW_ENFORCEMENT_VERSION,
            "review_disposition_version": summary.get("version") or disposition_service.REVIEW_DISPOSITION_VERSION,
            "review_disposition_set_sha256": summary.get("disposition_set_sha256") or "",
            "review_disposition_count": int(summary.get("expected_item_count") or 0),
        }
    )
    return identity


def _enforced_public_approval(
    approval: dict[str, Any],
    store: StorageAdapter | None = None,
    include_validation: bool = True,
) -> dict[str, Any]:
    result = deepcopy(_ORIGINALS["public_approval"](approval, store=store, include_validation=False))
    if not _is_enforced(approval):
        if include_validation:
            result["validation"] = _enforced_validate_mid_approval(approval, store=store)
        return result

    summary = _strict_review_disposition_summary(approval, store=store)
    decision = _dict(result.get("review_decision"))
    decision.update(
        {
            "review_disposition_set_sha256": _dict(approval.get("review_decision")).get("review_disposition_set_sha256") or "",
            "review_disposition_count": int(_dict(approval.get("review_decision")).get("review_disposition_count") or 0),
        }
    )
    result.update(
        {
            "approval_identity_sha256": approval.get("approval_identity_sha256") or "",
            "review_disposition_required": True,
            "review_disposition_policy_version": MID_REVIEW_ENFORCEMENT_VERSION,
            "review_disposition_set_sha256": approval.get("review_disposition_set_sha256") or "",
            "review_disposition_count": int(approval.get("review_disposition_count") or 0),
            "review_dispositions": summary,
            "review_decision": decision,
            "rule": "Approval is allowed only after every current exception has an exact-state item-level disposition. The finalized disposition-set hash is bound into the approval identity, approved artifact, delivery grant, and receipt.",
        }
    )
    approved_report = _dict(result.get("approved_report"))
    approved_report["review_disposition_set_sha256"] = _dict(approval.get("approved_report")).get("review_disposition_set_sha256") or ""
    result["approved_report"] = approved_report
    if include_validation:
        result["validation"] = _enforced_validate_mid_approval(approval, store=store)
    return result


def _enforced_transition_mid_approval(
    approval_id: str,
    state: str,
    actor: str,
    note: str = "",
    reviewed_item_ids: list[str] | None = None,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _active_store(store)
    approval = active.get("approvals", approval_id)
    requested = str(state or "").strip().lower()
    if not isinstance(approval, dict) or not _is_enforced(approval) or requested != "approved":
        return _ORIGINALS["transition_mid_approval"](
            approval_id,
            state,
            actor,
            note=note,
            reviewed_item_ids=reviewed_item_ids,
            admin_token=admin_token,
            store=active,
        )

    summary = _strict_review_disposition_summary(approval, store=active)
    if not summary.get("approval_ready"):
        return {
            "status": "blocked",
            "error": "Every current Mid review exception requires an approval-compatible item-level disposition before approval.",
            "review_dispositions": summary,
        }
    accepted = sorted(str(item) for item in _list(summary.get("accepted_item_ids")) if str(item))
    reviewed = sorted(set(str(item) for item in (reviewed_item_ids or []) if str(item)))
    if reviewed != accepted:
        return {
            "status": "blocked",
            "error": "The reviewed-item set must exactly match the accepted, current disposition set.",
            "missing_reviewed_item_ids": sorted(set(accepted) - set(reviewed)),
            "unexpected_reviewed_item_ids": sorted(set(reviewed) - set(accepted)),
            "review_dispositions": summary,
        }

    updated = deepcopy(approval)
    final_identity = _final_identity(updated, summary)
    updated["approval_identity"] = final_identity
    updated["approval_identity_sha256"] = _canonical_hash(final_identity)
    updated["review_disposition_set_sha256"] = summary.get("disposition_set_sha256") or ""
    updated["review_disposition_count"] = int(summary.get("expected_item_count") or 0)
    active.put("approvals", approval_id, updated)

    result = _ORIGINALS["transition_mid_approval"](
        approval_id,
        state,
        actor,
        note=note,
        reviewed_item_ids=accepted,
        admin_token=admin_token,
        store=active,
    )
    if result.get("status") != "approved":
        return result

    stored = active.get("approvals", approval_id)
    if not isinstance(stored, dict):
        return result
    finalized = deepcopy(stored)
    finalized_decision = _dict(finalized.get("review_decision"))
    finalized_decision.update(
        {
            "review_disposition_version": summary.get("version") or disposition_service.REVIEW_DISPOSITION_VERSION,
            "review_disposition_set_sha256": summary.get("disposition_set_sha256") or "",
            "review_disposition_count": int(summary.get("expected_item_count") or 0),
        }
    )
    finalized["review_decision"] = finalized_decision
    finalized_report = _dict(finalized.get("approved_report"))
    finalized_report["review_disposition_set_sha256"] = summary.get("disposition_set_sha256") or ""
    finalized_report["review_disposition_count"] = int(summary.get("expected_item_count") or 0)
    finalized["approved_report"] = finalized_report
    active.put("approvals", approval_id, finalized)
    active.audit(
        "mid.approval_review_dispositions_finalized",
        {
            "approval_id": approval_id,
            "run_id": finalized.get("run_id") or "",
            "approval_identity_sha256": finalized.get("approval_identity_sha256") or "",
            "review_disposition_set_sha256": summary.get("disposition_set_sha256") or "",
            "review_disposition_count": int(summary.get("expected_item_count") or 0),
        },
        customer_id=str(finalized.get("customer_id") or "default_customer"),
        project_id=str(finalized.get("project_id") or "default_project"),
    )
    return {
        **result,
        "approval": _enforced_public_approval(finalized, store=active),
    }


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "mid-assessment"))
    return cleaned.strip("-._") or "mid-assessment"


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = str(text or "").replace("\n", " ").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_enforced_pdf(report: dict[str, Any], approval: dict[str, Any], identity: dict[str, Any], summary: dict[str, Any]) -> bytes:
    payload = _dict(_dict(report.get("formats")).get("json"))
    sections = [item for item in _list(payload.get("sections")) if isinstance(item, dict)]
    decision = _dict(approval.get("review_decision"))
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=LETTER, pageCompression=1, invariant=1)
    width, height = LETTER
    left, right, top, bottom = 54, 54, 54, 48
    content_width = width - left - right
    y = height - top
    page = 0

    def header() -> None:
        nonlocal page, y
        page += 1
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(left, height - 28, "HUMAN REVIEWED - APPROVED - ITEM DECISIONS ENFORCED")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(width - right, 24, f"NICO Mid Assessment - Page {page}")
        canvas.line(left, height - 36, width - right, height - 36)
        canvas.line(left, 36, width - right, 36)
        y = height - top

    def ensure(required: float) -> None:
        nonlocal y
        if y - required < bottom:
            canvas.showPage()
            header()

    def paragraph(text: Any, font: str = "Helvetica", size: float = 9, leading: float = 12, after: float = 4) -> None:
        nonlocal y
        lines = _wrap(str(text or ""), font, size, content_width)
        ensure(len(lines) * leading + after)
        canvas.setFont(font, size)
        for line in lines:
            canvas.drawString(left, y, line)
            y -= leading
        y -= after

    def heading(text: str, size: float = 13) -> None:
        nonlocal y
        ensure(size + 12)
        y -= 4
        canvas.setFont("Helvetica-Bold", size)
        for line in _wrap(text, "Helvetica-Bold", size, content_width):
            canvas.drawString(left, y, line)
            y -= size + 4
        y -= 2

    def bullet(text: Any) -> None:
        nonlocal y
        lines = _wrap(str(text or ""), "Helvetica", 8.6, content_width - 18)
        ensure(len(lines) * 11 + 3)
        canvas.setFont("Helvetica", 8.6)
        canvas.drawString(left + 2, y, "-")
        for line in lines:
            canvas.drawString(left + 14, y, line)
            y -= 11
        y -= 2

    header()
    heading("NICO MID ASSESSMENT", 18)
    paragraph("Human-reviewed, snapshot-bound technical assessment", "Helvetica-Bold", 11, 14)
    paragraph(f"Repository: {report.get('repository') or ''}")
    paragraph(f"Mid run: {report.get('run_id') or ''}")
    paragraph(f"Snapshot commit: {report.get('snapshot_commit_sha') or ''}", size=8)
    heading("Approval certificate")
    bullet(f"Approval ID: {approval.get('approval_id') or ''}")
    bullet(f"Approved by: {decision.get('actor') or ''}")
    bullet(f"Approved at: {decision.get('decided_at') or ''}")
    bullet(f"Disposition-set SHA-256: {summary.get('disposition_set_sha256') or ''}")
    bullet(f"Item-level decisions: {summary.get('expected_item_count') or 0}")
    paragraph(decision.get("note") or "No final approval note recorded.")

    heading("Item-level review decisions")
    for item in _list(summary.get("items")):
        if not isinstance(item, dict):
            continue
        disposition = _dict(item.get("disposition"))
        heading(str(item.get("title") or item.get("item_id") or "Review item"), 10.5)
        paragraph(
            f"Decision: {item.get('decision_status') or 'pending'} | Section: {item.get('section_id') or 'report'} | Severity: {item.get('severity') or 'medium'}",
            "Helvetica-Bold",
            8.7,
            11,
        )
        paragraph(item.get("reason") or "No reason recorded.", size=8.5, leading=11)
        bullet(f"Reviewer: {disposition.get('actor') or ''}")
        bullet(f"Decided at: {disposition.get('decided_at') or ''}")
        bullet(f"Disposition SHA-256: {disposition.get('disposition_sha256') or ''}")
        paragraph(disposition.get("note") or "No item-level note recorded.", size=8.5, leading=11)

    heading("Assessment sections")
    for section in sections:
        heading(str(section.get("label") or section.get("id") or "Section"), 10.5)
        score = "Not scored" if section.get("score") is None else f"{section.get('score')}/100"
        paragraph(f"Truth status: {section.get('truth_status') or 'Unavailable'} | Score: {score}", "Helvetica-Bold", 8.7, 11)
        paragraph(section.get("summary") or "No supported conclusion was available.", size=8.5, leading=11)

    heading("Integrity identity")
    bullet(f"Approval record identity SHA-256: {approval.get('approval_identity_sha256') or ''}")
    bullet(f"Approved artifact identity SHA-256: {_canonical_hash(identity)}")
    bullet(f"Source draft PDF SHA-256: {identity.get('source_draft_pdf_sha256') or ''}")
    bullet(f"Review packet SHA-256: {identity.get('review_packet_sha256') or ''}")
    bullet(f"Disposition-set SHA-256: {identity.get('review_disposition_set_sha256') or ''}")
    bullet("Unsupported claims permitted: 0.")
    canvas.save()
    return buffer.getvalue()


def _public_disposition_items(summary: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in _list(summary.get("items")):
        if not isinstance(item, dict):
            continue
        disposition = _dict(item.get("disposition"))
        values.append(
            {
                "item_id": item.get("item_id") or "",
                "title": item.get("title") or "",
                "category": item.get("category") or "",
                "section_id": item.get("section_id") or "",
                "severity": item.get("severity") or "",
                "reason": item.get("reason") or "",
                "inference_based": bool(item.get("inference_based")),
                "score_change_material": bool(item.get("score_change_material")),
                "decision": item.get("decision_status") or "pending",
                "actor": disposition.get("actor") or "",
                "note": disposition.get("note") or "",
                "decided_at": disposition.get("decided_at") or "",
                "item_sha256": disposition.get("item_sha256") or "",
                "disposition_sha256": disposition.get("disposition_sha256") or "",
            }
        )
    return values


def _enforced_build_approved_report(report: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    if not _is_enforced(approval):
        return _ORIGINALS["build_mid_approved_report"](report, approval)
    if report.get("record_type") != "mid_assessment_report" or report.get("report_path") != approved_pdf_service.MID_REPORT_PATH:
        return {"status": "blocked", "error": "A valid Mid draft report is required."}
    draft_pdf = _decode_pdf(report)
    if not draft_pdf or hashlib.sha256(draft_pdf).hexdigest() != str(report.get("pdf_sha256") or ""):
        return {"status": "blocked", "error": "The Mid draft PDF failed integrity verification."}
    decision = _dict(approval.get("review_decision"))
    if approval.get("status") != "approved" or decision.get("state") != "approved":
        return {"status": "blocked", "error": "An approved Mid review decision is required."}
    summary = _strict_review_disposition_summary(approval)
    disposition_hash = str(summary.get("disposition_set_sha256") or "")
    if not summary.get("approval_ready") or disposition_hash != approval.get("review_disposition_set_sha256"):
        return {"status": "blocked", "error": "The item-level Mid review disposition set is incomplete or stale."}

    identity = {
        "approved_report_version": "mid-assessment-approved-v2",
        "report_type": approved_pdf_service.MID_REPORT_TYPE,
        "report_path": approved_pdf_service.MID_REPORT_PATH,
        "run_id": report.get("run_id") or "",
        "customer_id": report.get("customer_id") or "default_customer",
        "project_id": report.get("project_id") or "default_project",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "source_draft_report_id": report.get("report_id") or "",
        "source_draft_pdf_sha256": report.get("pdf_sha256") or "",
        "source_identity_sha256": report.get("source_identity_sha256") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "approval_id": approval.get("approval_id") or "",
        "approval_version": approval.get("approval_version") or "",
        "approval_record_identity_sha256": approval.get("approval_identity_sha256") or "",
        "approved_by": decision.get("actor") or "",
        "approved_at": decision.get("decided_at") or "",
        "approval_note_sha256": hashlib.sha256(str(decision.get("note") or "").encode("utf-8")).hexdigest(),
        "reviewed_item_ids": sorted(str(item) for item in _list(decision.get("reviewed_item_ids")) if str(item)),
        "review_disposition_version": summary.get("version") or disposition_service.REVIEW_DISPOSITION_VERSION,
        "review_disposition_set_sha256": disposition_hash,
        "review_disposition_count": int(summary.get("expected_item_count") or 0),
    }
    required = [
        "run_id", "snapshot_id", "snapshot_commit_sha", "source_draft_report_id", "source_draft_pdf_sha256",
        "source_identity_sha256", "review_packet_id", "review_packet_sha256", "approval_id",
        "approval_record_identity_sha256", "approved_by", "approved_at", "review_disposition_set_sha256",
    ]
    if any(not str(identity.get(key) or "") for key in required):
        return {"status": "blocked", "error": "The enforced approval identity is incomplete."}
    try:
        approved_pdf = _render_enforced_pdf(report, approval, identity, summary)
    except Exception as exc:
        return {"status": "blocked", "error": f"Approved Mid PDF rendering failed: {type(exc).__name__}."}
    if not approved_pdf.startswith(b"%PDF"):
        return {"status": "blocked", "error": "Approved Mid PDF rendering did not produce a valid PDF."}

    approved_hash = hashlib.sha256(approved_pdf).hexdigest()
    approved_id = f"mid_approved_report_{_canonical_hash(identity)[:24]}"
    disposition_items = _public_disposition_items(summary)
    return {
        "record_type": "mid_approved_report",
        "status": "complete",
        "approval_status": "approved",
        "report_version": "mid-assessment-approved-v2",
        "report_type": approved_pdf_service.MID_REPORT_TYPE,
        "report_path": approved_pdf_service.MID_REPORT_PATH,
        "report_id": approved_id,
        "run_id": report.get("run_id") or "",
        "customer_id": report.get("customer_id") or "default_customer",
        "project_id": report.get("project_id") or "default_project",
        "repository": report.get("repository") or "",
        "snapshot_id": report.get("snapshot_id") or "",
        "snapshot_commit_sha": report.get("snapshot_commit_sha") or "",
        "source_draft_report_id": report.get("report_id") or "",
        "source_draft_pdf_sha256": report.get("pdf_sha256") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "approval_id": approval.get("approval_id") or "",
        "approved_by": decision.get("actor") or "",
        "approved_at": decision.get("decided_at") or "",
        "approval_identity": identity,
        "approval_identity_sha256": _canonical_hash(identity),
        "approval_record_identity_sha256": approval.get("approval_identity_sha256") or "",
        "review_disposition_version": summary.get("version") or disposition_service.REVIEW_DISPOSITION_VERSION,
        "review_disposition_set_sha256": disposition_hash,
        "review_disposition_count": int(summary.get("expected_item_count") or 0),
        "review_dispositions": disposition_items,
        "pdf_sha256": approved_hash,
        "pdf_filename": f"nico-mid-assessment-{_safe_filename(report.get('repository') or 'repository')}-{_safe_filename(report.get('run_id') or '')}-APPROVED.pdf",
        "formats": {
            "json": {
                "status": "approved",
                "title": "NICO MID ASSESSMENT",
                "approval_label": "HUMAN REVIEWED - APPROVED - ITEM DECISIONS ENFORCED",
                "approval_identity": identity,
                "approval_identity_sha256": _canonical_hash(identity),
                "approval_record_identity_sha256": approval.get("approval_identity_sha256") or "",
                "source_draft_report_id": report.get("report_id") or "",
                "source_draft_pdf_sha256": report.get("pdf_sha256") or "",
                "review_packet_id": report.get("review_packet_id") or "",
                "review_packet_sha256": report.get("review_packet_sha256") or "",
                "review_disposition_version": summary.get("version") or disposition_service.REVIEW_DISPOSITION_VERSION,
                "review_disposition_set_sha256": disposition_hash,
                "review_disposition_count": int(summary.get("expected_item_count") or 0),
                "review_dispositions": disposition_items,
                "approved_by": decision.get("actor") or "",
                "approved_at": decision.get("decided_at") or "",
                "reviewed_item_ids": identity["reviewed_item_ids"],
                "human_review_required": False,
                "approved": True,
                "delivery_eligible": True,
                "client_delivery_allowed": False,
                "unsupported_claims_permitted": 0,
                "delivery_note": "A secure delivery grant has not been created. Client delivery remains disabled until the dedicated Mid delivery workflow verifies this approved artifact and its disposition-set hash.",
            },
            "pdf": base64.b64encode(approved_pdf).decode("ascii"),
        },
        "human_review_required": False,
        "approved": True,
        "delivery_eligible": True,
        "client_delivery_allowed": False,
        "delivery_status": "not_configured",
        "unsupported_claims_permitted": 0,
    }


def _enforced_artifact_identity(report: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    identity = deepcopy(_ORIGINALS["artifact_identity"](report, approval))
    if _is_enforced(approval):
        identity.update(
            {
                "approval_record_identity_sha256": approval.get("approval_identity_sha256") or "",
                "review_disposition_version": report.get("review_disposition_version") or "",
                "review_disposition_set_sha256": report.get("review_disposition_set_sha256") or "",
                "review_disposition_count": int(report.get("review_disposition_count") or 0),
            }
        )
    return identity


def _enforced_approved_artifact(run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
    artifact = _ORIGINALS["approved_artifact"](run_id, customer_id, project_id)
    if artifact.get("status") != "verified":
        return artifact
    approval = _dict(artifact.get("approval"))
    if not _is_enforced(approval):
        return artifact
    report = _dict(artifact.get("report"))
    summary = _strict_review_disposition_summary(approval)
    disposition_hash = str(summary.get("disposition_set_sha256") or "")
    valid = bool(
        summary.get("approval_ready")
        and disposition_hash
        and approval.get("review_disposition_set_sha256") == disposition_hash
        and _dict(approval.get("approval_identity")).get("review_disposition_set_sha256") == disposition_hash
        and _dict(approval.get("review_decision")).get("review_disposition_set_sha256") == disposition_hash
        and _dict(approval.get("approved_report")).get("review_disposition_set_sha256") == disposition_hash
        and report.get("review_disposition_set_sha256") == disposition_hash
        and _dict(_dict(report.get("formats")).get("json")).get("review_disposition_set_sha256") == disposition_hash
        and report.get("approval_record_identity_sha256") == approval.get("approval_identity_sha256")
    )
    if not valid:
        return {"status": "blocked", "error": "The approved Mid artifact failed item-level review-disposition integrity verification."}
    return artifact


def _enforced_public_access(record: Any) -> dict[str, Any]:
    result = deepcopy(_ORIGINALS["public_access"](record))
    value = record if isinstance(record, dict) else {}
    identity = _dict(value.get("artifact_identity"))
    disposition_hash = value.get("review_disposition_set_sha256") or identity.get("review_disposition_set_sha256") or ""
    if disposition_hash:
        result["review_disposition_set_sha256"] = disposition_hash
        result["review_disposition_count"] = int(identity.get("review_disposition_count") or 0)
        result["approval_record_identity_sha256"] = identity.get("approval_record_identity_sha256") or ""
    return result


def _enforced_public_receipt(record: Any) -> dict[str, Any]:
    result = deepcopy(_ORIGINALS["public_receipt"](record))
    value = record if isinstance(record, dict) else {}
    if value.get("review_disposition_set_sha256"):
        result["review_disposition_set_sha256"] = value.get("review_disposition_set_sha256") or ""
        result["review_disposition_count"] = int(value.get("review_disposition_count") or 0)
        result["approval_record_identity_sha256"] = value.get("approval_record_identity_sha256") or ""
    return result


def _enforced_put_receipt(record: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(record)
    access = delivery_service._get_access(str(updated.get("access_id") or ""))
    identity = _dict(_dict(access).get("artifact_identity"))
    disposition_hash = str(identity.get("review_disposition_set_sha256") or "")
    if disposition_hash:
        updated["review_disposition_set_sha256"] = disposition_hash
        updated["review_disposition_count"] = int(identity.get("review_disposition_count") or 0)
        updated["approval_record_identity_sha256"] = identity.get("approval_record_identity_sha256") or ""
        core = {key: value for key, value in updated.items() if key != "receipt_sha256"}
        updated["receipt_sha256"] = _canonical_hash(core)
    return _ORIGINALS["put_receipt"](updated)


def _enforced_inspect_delivery(token: Any) -> dict[str, Any]:
    result = deepcopy(_ORIGINALS["inspect_delivery"](token))
    if result.get("status") == "available":
        access = _dict(result.get("access"))
        disposition_hash = str(access.get("review_disposition_set_sha256") or "")
        if disposition_hash:
            delivery = _dict(result.get("delivery"))
            delivery["review_disposition_set_sha256"] = disposition_hash
            delivery["review_disposition_count"] = int(access.get("review_disposition_count") or 0)
            result["delivery"] = delivery
    return result


def _enforced_redeem_delivery(token: Any, recipient_name: str, acknowledged: bool, acknowledgement_text: str) -> dict[str, Any]:
    result = deepcopy(_ORIGINALS["redeem_delivery"](token, recipient_name, acknowledged, acknowledgement_text))
    receipt = _dict(result.get("receipt"))
    disposition_hash = str(receipt.get("review_disposition_set_sha256") or "")
    if disposition_hash:
        result["review_disposition_set_sha256"] = disposition_hash
        result["review_disposition_count"] = int(receipt.get("review_disposition_count") or 0)
        STORE.audit(
            "mid.delivery_review_disposition_verified",
            {
                "receipt_id": receipt.get("receipt_id") or "",
                "access_id": receipt.get("access_id") or "",
                "approval_id": receipt.get("approval_id") or "",
                "review_disposition_set_sha256": disposition_hash,
                "review_disposition_count": int(receipt.get("review_disposition_count") or 0),
            },
        )
    return result


def install_mid_review_enforcement() -> dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {"installed": True, "idempotent_reuse": True, "approval_version": MID_APPROVAL_ENFORCED_VERSION}

    _ORIGINALS.update(
        {
            "review_disposition_summary": disposition_service.review_disposition_summary,
            "validate_mid_approval": approval_service.validate_mid_approval,
            "request_mid_approval": approval_service.request_mid_approval,
            "transition_mid_approval": approval_service.transition_mid_approval,
            "public_approval": approval_service._public_approval,
            "build_mid_approved_report": approval_service.build_mid_approved_report,
            "artifact_identity": delivery_service._artifact_identity,
            "approved_artifact": delivery_service._approved_artifact,
            "public_access": delivery_service._public_access,
            "public_receipt": delivery_service._public_receipt,
            "put_receipt": delivery_service._put_receipt,
            "inspect_delivery": delivery_service.inspect_mid_delivery_access,
            "redeem_delivery": delivery_service.redeem_mid_delivery_access,
        }
    )

    approval_service.MID_APPROVAL_VERSION = MID_APPROVAL_ENFORCED_VERSION
    disposition_service.review_disposition_summary = _strict_review_disposition_summary
    approval_service.validate_mid_approval = _enforced_validate_mid_approval
    approval_service._public_approval = _enforced_public_approval
    approval_service.request_mid_approval = _enforced_request_mid_approval
    approval_service.transition_mid_approval = _enforced_transition_mid_approval
    approval_service.build_mid_approved_report = _enforced_build_approved_report

    approval_api.request_mid_approval = _enforced_request_mid_approval
    approval_api.transition_mid_approval = _enforced_transition_mid_approval

    delivery_service._artifact_identity = _enforced_artifact_identity
    delivery_service._approved_artifact = _enforced_approved_artifact
    delivery_service._public_access = _enforced_public_access
    delivery_service._public_receipt = _enforced_public_receipt
    delivery_service._put_receipt = _enforced_put_receipt
    delivery_service.inspect_mid_delivery_access = _enforced_inspect_delivery
    delivery_service.redeem_mid_delivery_access = _enforced_redeem_delivery

    try:
        import nico.mid_delivery_api as delivery_api

        if hasattr(delivery_api, "inspect_mid_delivery_access"):
            delivery_api.inspect_mid_delivery_access = _enforced_inspect_delivery
        if hasattr(delivery_api, "redeem_mid_delivery_access"):
            delivery_api.redeem_mid_delivery_access = _enforced_redeem_delivery
    except Exception:
        pass

    _INSTALLED = True
    return {
        "installed": True,
        "idempotent_reuse": False,
        "approval_version": MID_APPROVAL_ENFORCED_VERSION,
        "enforcement_version": MID_REVIEW_ENFORCEMENT_VERSION,
        "legacy_versions_supported": sorted(MID_APPROVAL_LEGACY_VERSIONS),
    }


__all__ = [
    "MID_APPROVAL_ENFORCED_VERSION",
    "MID_APPROVAL_LEGACY_VERSIONS",
    "MID_REVIEW_ENFORCEMENT_VERSION",
    "install_mid_review_enforcement",
]
