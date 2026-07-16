from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_TRUTH_IDENTITY_CONSISTENCY_VERSION = "nico.mid_truth_identity_consistency.v1"
_PACKET_MARKER = "_nico_mid_truth_identity_packet_v1"
_REPORT_MARKER = "_nico_mid_truth_identity_report_v1"
_APPROVAL_MARKER = "_nico_mid_truth_identity_approval_v1"
_TERMINAL_MARKER = "_nico_mid_truth_identity_terminal_v1"
_STALE_MARKERS = (
    "stale relative to the current truth model",
    "stale relative to the current review packet",
)
_COMPLETE = {"complete", "completed", "attached", "verified"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _section_hashes(truth: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("id") or f"section_{index}"): _canonical_hash(item)
        for index, item in enumerate(_list(truth.get("sections")))
        if isinstance(item, dict)
    }


def _changed_section_ids(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    first = _section_hashes(before)
    second = _section_hashes(after)
    return sorted(section_id for section_id in set(first) | set(second) if first.get(section_id) != second.get(section_id))


def _scope_matches(run: dict[str, Any], customer_id: str = "", project_id: str = "") -> bool:
    request = _dict(run.get("request"))
    stored_customer = str(run.get("customer_id") or request.get("customer_id") or "default_customer")
    stored_project = str(run.get("project_id") or request.get("project_id") or "default_project")
    return (not customer_id or customer_id == stored_customer) and (not project_id or project_id == stored_project)


def canonicalize_mid_truth(
    run_id: str,
    *,
    customer_id: str = "",
    project_id: str = "",
    store: Any = None,
    persist: bool = True,
) -> dict[str, Any]:
    from nico.mid_assessment_runs import load_mid_assessment_run
    from nico.mid_optional_evidence import optional_evidence_summary
    from nico.mid_truth_status import attach_mid_truth_status
    from nico.storage import STORE, utc_now

    active = store or STORE
    run = load_mid_assessment_run(str(run_id or ""), store=active)
    if not isinstance(run, dict):
        return {"status": "not_found", "run_id": run_id}
    if not _scope_matches(run, str(customer_id or ""), str(project_id or "")):
        return {"status": "not_found", "run_id": run_id}

    response = deepcopy(_dict(run.get("response")))
    prior_truth = deepcopy(_dict(response.get("mid_truth_status")))
    prior_hash = _canonical_hash(prior_truth) if prior_truth else ""
    response["optional_evidence"] = optional_evidence_summary(str(run_id), store=active)
    attach_mid_truth_status(response)
    current_truth = deepcopy(_dict(response.get("mid_truth_status")))
    current_hash = _canonical_hash(current_truth) if current_truth else ""
    changed_sections = _changed_section_ids(prior_truth, current_truth)
    changed = prior_hash != current_hash

    updated_run = deepcopy(run)
    if persist and current_truth:
        updated_run["response"] = response
        updated_run["updated_at"] = utc_now()
        active.put("assessment_runs", str(run_id), updated_run)

    return {
        "status": "canonical",
        "run_id": str(run_id),
        "run": updated_run,
        "truth": current_truth,
        "prior_truth_sha256": prior_hash,
        "truth_sha256": current_hash,
        "truth_changed": changed,
        "changed_section_ids": changed_sections,
        "optional_evidence_status": _dict(response.get("optional_evidence")).get("status") or "unknown",
        "persisted": bool(persist and current_truth),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _approval_error(result: dict[str, Any]) -> str:
    direct = str(result.get("error") or result.get("message") or "")
    if direct:
        return direct
    for item in _list(result.get("progress")):
        if isinstance(item, dict) and str(item.get("step") or "") == "approval_request":
            return str(item.get("message") or "")
    return ""


def _stale_approval_error(value: Any) -> bool:
    text = " ".join(str(value or "").lower().split())
    return any(marker in text for marker in _STALE_MARKERS)


def _progress_status(response: dict[str, Any], step: str) -> str:
    for item in _list(response.get("progress")):
        if isinstance(item, dict) and str(item.get("step") or "") == step:
            return str(item.get("status") or "").lower()
    return ""


def _set_progress_step(
    response: dict[str, Any],
    step: str,
    status: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    progress = [deepcopy(item) for item in _list(response.get("progress")) if isinstance(item, dict)]
    replacement = {
        "step": step,
        "status": status,
        "message": message,
        "evidence": deepcopy(evidence or {}),
    }
    for index, item in enumerate(progress):
        if str(item.get("step") or "") == step:
            progress[index] = replacement
            response["progress"] = progress
            return
    progress.append(replacement)
    response["progress"] = progress


def _scanner_complete(response: dict[str, Any]) -> bool:
    scanner = _dict(response.get("scanner"))
    evidence = _dict(response.get("scanner_evidence"))
    values = {
        str(scanner.get("status") or "").lower(),
        str(evidence.get("status") or "").lower(),
        str(evidence.get("scanner_status") or "").lower(),
        _progress_status(response, "scanner_reconciliation"),
    }
    return bool(values & _COMPLETE)


def _quality_gate_allows_review(report: dict[str, Any]) -> bool:
    if str(report.get("status") or "").lower() != "complete":
        return False
    manifest = _dict(report.get("report_quality_manifest"))
    if not manifest:
        return True
    return str(manifest.get("status") or "").lower() in {"ready_for_human_review", "review_required", "complete", "passed"}


def _repairable_stale_record(record: dict[str, Any], store: Any) -> bool:
    response = _dict(record.get("response"))
    if str(response.get("report_generation_status") or "").lower() != "complete":
        return False
    if str(response.get("approval_request_status") or "").lower() != "blocked":
        return False
    if not _stale_approval_error(_approval_error(response)):
        return False
    if not _scanner_complete(response):
        return False
    if _progress_status(response, "scoring") not in _COMPLETE:
        return False
    report_id = str(_dict(response.get("mid_report")).get("report_id") or record.get("report_id") or "")
    report = store.get("reports", report_id) if report_id else None
    return isinstance(report, dict) and _quality_gate_allows_review(report)


def _report_summary(report: dict[str, Any]) -> dict[str, Any]:
    formats = _dict(report.get("formats"))
    return {
        "status": "complete",
        "draft_status": report.get("draft_status") or "human_review_required",
        "report_id": report.get("report_id") or "",
        "report_path": report.get("report_path") or "mid_run",
        "report_version": report.get("report_version") or "",
        "pdf_sha256": report.get("pdf_sha256") or "",
        "pdf_filename": report.get("pdf_filename") or "",
        "review_packet_id": report.get("review_packet_id") or "",
        "review_packet_sha256": report.get("review_packet_sha256") or "",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "formats_available": sorted(key for key, value in formats.items() if value),
    }


def _public_report_formats(report: dict[str, Any]) -> dict[str, Any]:
    formats = _dict(report.get("formats"))
    return {
        "markdown": str(formats.get("markdown") or ""),
        "html": str(formats.get("html") or ""),
        "pdf_base64": str(formats.get("pdf") or ""),
        "pdf_filename": str(report.get("pdf_filename") or "nico-mid-assessment-DRAFT.pdf"),
        "pdf_sha256": str(report.get("pdf_sha256") or ""),
    }


def repair_stale_mid_approval(record: dict[str, Any], *, store: Any = None) -> dict[str, Any] | None:
    from nico import mid_assessment_approval
    from nico import mid_assessment_runs
    from nico.storage import STORE, utc_now

    active = store or STORE
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        return None
    if not _repairable_stale_record(record, active):
        return None

    run_id = str(record.get("run_id") or "")
    customer_id = str(record.get("customer_id") or "default_customer")
    project_id = str(record.get("project_id") or "default_project")
    response = deepcopy(_dict(record.get("response")))
    prior_report_id = str(_dict(response.get("mid_report")).get("report_id") or record.get("report_id") or "")

    # The core repository/scanner/scoring lifecycle completed. Only the derived
    # report/review identity chain is repaired; no repository or scanner work is
    # re-entered and no replacement run is created.
    staged_record = deepcopy(record)
    staged_record["status"] = "complete"
    response["status"] = "complete"
    response["approval_request_status"] = "repairing"
    response["current_stage"] = "approval_request"
    response["continuation_required"] = False
    response["recovery_required"] = False
    _set_progress_step(
        response,
        "approval_request",
        "running",
        "NICO is rebuilding the exact Mid report/review identity chain from the retained run without rescanning the repository.",
        {
            "same_run_id": run_id,
            "repository_recaptured": False,
            "scanner_rerun": False,
            "score_recomputed": False,
            "client_delivery_allowed": False,
        },
    )
    staged_record["response"] = mid_assessment_runs._retained_response(response)
    staged_record["updated_at"] = utc_now()
    active.put("assessment_runs", run_id, staged_record)

    canonical = canonicalize_mid_truth(
        run_id,
        customer_id=customer_id,
        project_id=project_id,
        store=active,
        persist=True,
    )
    approval_result = mid_assessment_approval.request_mid_approval(
        run_id,
        customer_id,
        project_id,
        admin_token=mid_assessment_approval.internal_admin_token() if hasattr(mid_assessment_approval, "internal_admin_token") else "",
        store=active,
    )
    # request_mid_approval normally receives the server token through the API
    # module. Import the canonical token directly when the approval module does
    # not expose it.
    if approval_result.get("status") != "requested":
        from nico.admin_security import internal_admin_token

        approval_result = mid_assessment_approval.request_mid_approval(
            run_id,
            customer_id,
            project_id,
            admin_token=internal_admin_token(),
            store=active,
        )

    approval = _dict(approval_result.get("approval"))
    if approval_result.get("status") != "requested" or not approval:
        failed = active.get("assessment_runs", run_id) or staged_record
        failed_response = deepcopy(_dict(failed.get("response")))
        message = str(approval_result.get("error") or "The exact Mid human-review request could not be repaired.")
        failed_response["status"] = "blocked"
        failed_response["approval_request_status"] = "blocked"
        failed_response["approval_request_error"] = message
        failed_response["approval_request_error_code"] = str(approval_result.get("code") or "mid_approval_repair_failed")
        failed_response["same_run_approval_repair"] = {
            "status": "blocked",
            "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
            "prior_report_id": prior_report_id,
            "truth_sha256": canonical.get("truth_sha256") or "",
            "changed_section_ids": canonical.get("changed_section_ids") or [],
            "repository_recaptured": False,
            "scanner_rerun": False,
            "replacement_run_created": False,
            "duplicate_start_allowed": False,
        }
        _set_progress_step(failed_response, "approval_request", "blocked", message, failed_response["same_run_approval_repair"])
        failed["status"] = "blocked"
        failed["response"] = mid_assessment_runs._retained_response(failed_response)
        failed["updated_at"] = utc_now()
        active.put("assessment_runs", run_id, failed)
        return failed_response

    report_id = str(approval.get("draft_report_id") or "")
    report = active.get("reports", report_id) if report_id else None
    if not isinstance(report, dict):
        return None

    repaired_record = active.get("assessment_runs", run_id) or staged_record
    repaired_response = deepcopy(_dict(repaired_record.get("response")))
    repaired_response["status"] = "complete"
    repaired_response["current_stage"] = "complete"
    repaired_response["progress_percent"] = 100
    repaired_response["report_generation_status"] = "complete"
    repaired_response["mid_report"] = _report_summary(report)
    repaired_response["reports"] = _public_report_formats(report)
    repaired_response["approval_request"] = approval
    repaired_response["approval_request_status"] = "pending"
    repaired_response.pop("approval_request_error", None)
    repaired_response.pop("approval_request_error_code", None)
    repaired_response["continuation_required"] = False
    repaired_response["recovery_required"] = False
    repaired_response["same_run_approval_repair"] = {
        "status": "complete",
        "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
        "prior_report_id": prior_report_id,
        "current_report_id": report_id,
        "approval_id": approval.get("approval_id") or "",
        "truth_sha256": canonical.get("truth_sha256") or "",
        "truth_changed": bool(canonical.get("truth_changed")),
        "changed_section_ids": canonical.get("changed_section_ids") or [],
        "repository_recaptured": False,
        "scanner_rerun": False,
        "score_recomputed": False,
        "replacement_run_created": False,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    _set_progress_step(
        repaired_response,
        "approval_request",
        "complete",
        "Exact-state Mid human-review request created from the canonical retained truth model; reviewer decision remains mandatory.",
        {
            "approval_id": approval.get("approval_id") or "",
            "draft_report_id": report_id,
            "same_run_identity_preserved": True,
            "repository_recaptured": False,
            "scanner_rerun": False,
            "human_approval_required": True,
            "client_delivery_allowed": False,
        },
    )
    for stage in _list(repaired_response.get("execution_stages")):
        if isinstance(stage, dict) and str(stage.get("id") or "") == "dedicated_mid_draft_and_review_request":
            stage["status"] = "complete"
            stage["report_id"] = report_id
            stage["approval_id"] = approval.get("approval_id") or ""

    repaired_record["status"] = "complete"
    repaired_record["report_id"] = report_id
    repaired_record["approval_id"] = str(approval.get("approval_id") or "")
    repaired_record["response"] = mid_assessment_runs._retained_response(repaired_response)
    repaired_record["updated_at"] = utc_now()
    active.put("assessment_runs", run_id, repaired_record)
    active.audit(
        "mid.approval_identity_repaired",
        {
            "run_id": run_id,
            "prior_report_id": prior_report_id,
            "current_report_id": report_id,
            "approval_id": approval.get("approval_id") or "",
            "truth_sha256": canonical.get("truth_sha256") or "",
            "changed_section_ids": canonical.get("changed_section_ids") or [],
            "repository_recaptured": False,
            "scanner_rerun": False,
            "replacement_run_created": False,
            "client_delivery_allowed": False,
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    repaired_response["run_id"] = run_id
    repaired_response["customer_id"] = customer_id
    repaired_response["project_id"] = project_id
    repaired_response["repository"] = str(repaired_record.get("repository") or repaired_response.get("repository") or "")
    repaired_response["status_refresh"] = True
    return repaired_response


def install_mid_truth_identity_consistency() -> dict[str, Any]:
    from nico import mid_assessment_api
    from nico import mid_assessment_approval
    from nico import mid_assessment_report
    from nico import mid_review_by_exception
    from nico import mid_terminal_truth_patch

    packet_current: Callable[..., dict[str, Any]] = mid_review_by_exception.build_mid_review_packet
    packet_installed = False
    if not getattr(packet_current, _PACKET_MARKER, False):
        @wraps(packet_current)
        def packet_with_canonical_truth(run_id: str, customer_id: str, project_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            canonicalize_mid_truth(
                run_id,
                customer_id=customer_id,
                project_id=project_id,
                store=kwargs.get("store"),
                persist=True,
            )
            return packet_current(run_id, customer_id, project_id, *args, **kwargs)

        setattr(packet_with_canonical_truth, _PACKET_MARKER, True)
        setattr(packet_with_canonical_truth, "_nico_previous", packet_current)
        mid_review_by_exception.build_mid_review_packet = packet_with_canonical_truth
        mid_assessment_report.build_mid_review_packet = packet_with_canonical_truth
        mid_assessment_approval.build_mid_review_packet = packet_with_canonical_truth
        packet_installed = True

    report_current: Callable[..., dict[str, Any]] = mid_assessment_report.generate_mid_draft_report
    report_installed = False
    if not getattr(report_current, _REPORT_MARKER, False):
        @wraps(report_current)
        def report_with_canonical_truth(run_id: str, customer_id: str, project_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            canonicalize_mid_truth(
                run_id,
                customer_id=customer_id,
                project_id=project_id,
                store=kwargs.get("store"),
                persist=True,
            )
            return report_current(run_id, customer_id, project_id, *args, **kwargs)

        setattr(report_with_canonical_truth, _REPORT_MARKER, True)
        setattr(report_with_canonical_truth, "_nico_previous", report_current)
        mid_assessment_report.generate_mid_draft_report = report_with_canonical_truth
        mid_assessment_api.generate_mid_draft_report = report_with_canonical_truth
        mid_assessment_approval.generate_mid_draft_report = report_with_canonical_truth
        report_installed = True

    approval_current: Callable[..., dict[str, Any]] = mid_assessment_approval.request_mid_approval
    approval_installed = False
    if not getattr(approval_current, _APPROVAL_MARKER, False):
        @wraps(approval_current)
        def approval_with_canonical_truth(run_id: str, customer_id: str, project_id: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            first = canonicalize_mid_truth(
                run_id,
                customer_id=customer_id,
                project_id=project_id,
                store=kwargs.get("store"),
                persist=True,
            )
            result = approval_current(run_id, customer_id, project_id, *args, **kwargs)
            if result.get("status") == "blocked" and _stale_approval_error(result.get("error")):
                second = canonicalize_mid_truth(
                    run_id,
                    customer_id=customer_id,
                    project_id=project_id,
                    store=kwargs.get("store"),
                    persist=True,
                )
                result = approval_current(run_id, customer_id, project_id, *args, **kwargs)
                if result.get("status") == "blocked":
                    result = deepcopy(result)
                    result["code"] = "mid_approval_identity_still_stale"
                    result["truth_identity_diagnostics"] = {
                        "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
                        "first_truth_sha256": first.get("truth_sha256") or "",
                        "second_truth_sha256": second.get("truth_sha256") or "",
                        "truth_changed_between_attempts": first.get("truth_sha256") != second.get("truth_sha256"),
                        "changed_section_ids": second.get("changed_section_ids") or [],
                        "retry_count": 1,
                        "duplicate_start_allowed": False,
                        "client_delivery_allowed": False,
                    }
            return result

        setattr(approval_with_canonical_truth, _APPROVAL_MARKER, True)
        setattr(approval_with_canonical_truth, "_nico_previous", approval_current)
        mid_assessment_approval.request_mid_approval = approval_with_canonical_truth
        mid_assessment_api.request_mid_approval = approval_with_canonical_truth
        approval_installed = True

    terminal_current: Callable[[dict[str, Any]], dict[str, Any] | None] = mid_terminal_truth_patch._terminal_retained_response
    terminal_installed = False
    if not getattr(terminal_current, _TERMINAL_MARKER, False):
        @wraps(terminal_current)
        def terminal_with_same_run_repair(record: dict[str, Any]) -> dict[str, Any] | None:
            repaired = repair_stale_mid_approval(record)
            if repaired is not None:
                return repaired
            return terminal_current(record)

        setattr(terminal_with_same_run_repair, _TERMINAL_MARKER, True)
        setattr(terminal_with_same_run_repair, "_nico_previous", terminal_current)
        mid_terminal_truth_patch._terminal_retained_response = terminal_with_same_run_repair
        terminal_installed = True

    return {
        "status": "installed" if packet_installed or report_installed or approval_installed or terminal_installed else "already_installed",
        "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
        "canonical_truth_before_packet": True,
        "canonical_truth_before_report": True,
        "canonical_truth_before_approval": True,
        "bounded_stale_retry_count": 1,
        "same_run_stale_approval_repair": True,
        "repository_recaptured_during_repair": False,
        "scanner_rerun_during_repair": False,
        "replacement_run_created": False,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_TRUTH_IDENTITY_CONSISTENCY_VERSION",
    "canonicalize_mid_truth",
    "install_mid_truth_identity_consistency",
    "repair_stale_mid_approval",
]
