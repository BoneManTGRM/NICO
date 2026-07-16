from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_TRUTH_IDENTITY_CONSISTENCY_VERSION = "nico.mid_truth_identity_consistency.v2"
_SOURCE_IDENTITY_MARKER = "_nico_mid_semantic_source_identity_v2"
_SOURCE_PACKET_MARKER = "_nico_mid_semantic_source_packet_v2"
_CURRENT_TRUTH_MARKER = "_nico_mid_semantic_current_truth_v2"
_APPROVAL_MARKER = "_nico_mid_semantic_approval_v2"
_TERMINAL_MARKER = "_nico_mid_semantic_terminal_v2"
_STALE_MARKERS = (
    "stale relative to the current truth model",
    "stale relative to the current review packet",
)
_COMPLETE = {"complete", "completed", "attached", "verified"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _list_sort_key(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("id", "item_id", "entry_id", "section_id", "tool", "name", "code"):
            if value.get(key) not in (None, ""):
                return f"{key}:{value.get(key)}|{_canonical_json(value)}"
    return _canonical_json(value)


def canonical_mid_truth_payload(value: Any) -> Any:
    """Return a deterministic, lossless representation of Mid truth evidence.

    Dictionary ordering and list ordering are normalized, but no truth field is
    removed, upgraded, or rewritten. Substantive changes—including optional
    evidence, section status, findings, limitations, scores, coverage, or the
    unsupported-claims boundary—therefore continue to change the identity.
    """

    if isinstance(value, dict):
        return {
            str(key): canonical_mid_truth_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        normalized = [canonical_mid_truth_payload(item) for item in value]
        return sorted(normalized, key=_list_sort_key)
    if isinstance(value, tuple):
        return canonical_mid_truth_payload(list(value))
    if isinstance(value, set):
        return canonical_mid_truth_payload(list(value))
    if isinstance(value, float) and not (value == value and abs(value) != float("inf")):
        return str(value)
    return deepcopy(value)


def semantic_mid_truth_hash(truth: Any) -> str:
    return _canonical_hash(canonical_mid_truth_payload(truth))


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
    return str(manifest.get("status") or "").lower() in {
        "ready_for_human_review",
        "review_required",
        "complete",
        "passed",
    }


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
        "truth_sha256": _dict(report.get("source_identity")).get("truth_sha256") or "",
        "truth_identity_version": _dict(report.get("source_identity")).get("truth_identity_version") or "",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "formats_available": sorted(key for key, item in formats.items() if item),
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
    """Repair only a stale report/review identity chain on the exact retained run."""

    from nico import mid_assessment_approval, mid_assessment_runs
    from nico.admin_security import internal_admin_token
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
    prior_report = active.get("reports", prior_report_id) if prior_report_id else {}
    prior_truth_hash = str(_dict(_dict(prior_report).get("source_identity")).get("truth_sha256") or "")

    staged = deepcopy(record)
    staged["status"] = "complete"
    response["status"] = "complete"
    response["approval_request_status"] = "repairing"
    response["current_stage"] = "approval_request"
    response["continuation_required"] = False
    response["recovery_required"] = False
    _set_progress_step(
        response,
        "approval_request",
        "running",
        "NICO is rebuilding the exact Mid report/review identity chain from retained evidence without rescanning the repository.",
        {
            "same_run_id": run_id,
            "repository_recaptured": False,
            "scanner_rerun": False,
            "score_recomputed": False,
            "replacement_run_created": False,
            "client_delivery_allowed": False,
        },
    )
    staged["response"] = mid_assessment_runs._retained_response(response)
    staged["updated_at"] = utc_now()
    active.put("assessment_runs", run_id, staged)

    approval_result = mid_assessment_approval.request_mid_approval(
        run_id,
        customer_id,
        project_id,
        admin_token=internal_admin_token(),
        store=active,
    )
    approval = _dict(approval_result.get("approval"))
    if approval_result.get("status") != "requested" or not approval:
        failed = active.get("assessment_runs", run_id) or staged
        failed_response = deepcopy(_dict(failed.get("response")))
        message = str(approval_result.get("error") or "The exact Mid human-review request could not be repaired.")
        failed_response["status"] = "blocked"
        failed_response["approval_request_status"] = "blocked"
        failed_response["approval_request_error"] = message
        failed_response["approval_request_error_code"] = str(
            approval_result.get("code") or "mid_approval_identity_repair_failed"
        )
        failed_response["same_run_approval_repair"] = {
            "status": "blocked",
            "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
            "prior_report_id": prior_report_id,
            "prior_truth_sha256": prior_truth_hash,
            "diagnostics": deepcopy(approval_result.get("truth_identity_diagnostics") or {}),
            "repository_recaptured": False,
            "scanner_rerun": False,
            "score_recomputed": False,
            "replacement_run_created": False,
            "duplicate_start_allowed": False,
            "client_delivery_allowed": False,
        }
        _set_progress_step(
            failed_response,
            "approval_request",
            "blocked",
            message,
            failed_response["same_run_approval_repair"],
        )
        failed["status"] = "blocked"
        failed["response"] = mid_assessment_runs._retained_response(failed_response)
        failed["updated_at"] = utc_now()
        active.put("assessment_runs", run_id, failed)
        return failed_response

    report_id = str(approval.get("draft_report_id") or "")
    report = active.get("reports", report_id) if report_id else None
    if not isinstance(report, dict) or not _quality_gate_allows_review(report):
        return None

    current_truth_hash = str(_dict(report.get("source_identity")).get("truth_sha256") or "")
    repaired_record = active.get("assessment_runs", run_id) or staged
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
        "prior_truth_sha256": prior_truth_hash,
        "current_truth_sha256": current_truth_hash,
        "report_regenerated": report_id != prior_report_id,
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
        "Exact-state Mid human-review request created from the canonical retained truth identity; reviewer decision remains mandatory.",
        {
            "approval_id": approval.get("approval_id") or "",
            "draft_report_id": report_id,
            "same_run_identity_preserved": True,
            "repository_recaptured": False,
            "scanner_rerun": False,
            "score_recomputed": False,
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
            "prior_truth_sha256": prior_truth_hash,
            "current_truth_sha256": current_truth_hash,
            "repository_recaptured": False,
            "scanner_rerun": False,
            "score_recomputed": False,
            "replacement_run_created": False,
            "client_delivery_allowed": False,
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    repaired_response["run_id"] = run_id
    repaired_response["customer_id"] = customer_id
    repaired_response["project_id"] = project_id
    repaired_response["repository"] = str(
        repaired_record.get("repository") or repaired_response.get("repository") or ""
    )
    repaired_response["status_refresh"] = True
    return repaired_response


def install_mid_truth_identity_consistency() -> dict[str, Any]:
    from nico import mid_assessment_api, mid_assessment_approval, mid_assessment_report
    from nico import mid_review_by_exception, mid_terminal_truth_patch

    source_identity_current: Callable[..., dict[str, Any]] = mid_assessment_report._source_identity
    source_identity_installed = False
    if not getattr(source_identity_current, _SOURCE_IDENTITY_MARKER, False):
        @wraps(source_identity_current)
        def semantic_source_identity(
            record: dict[str, Any],
            packet: dict[str, Any],
            truth: dict[str, Any],
        ) -> dict[str, Any]:
            identity = deepcopy(source_identity_current(record, packet, truth))
            identity["truth_sha256"] = semantic_mid_truth_hash(truth)
            identity["truth_identity_version"] = MID_TRUTH_IDENTITY_CONSISTENCY_VERSION
            return identity

        setattr(semantic_source_identity, _SOURCE_IDENTITY_MARKER, True)
        setattr(semantic_source_identity, "_nico_previous", source_identity_current)
        mid_assessment_report._source_identity = semantic_source_identity
        source_identity_installed = True

    source_packet_current: Callable[..., dict[str, Any]] = mid_review_by_exception._source_packet
    source_packet_installed = False
    if not getattr(source_packet_current, _SOURCE_PACKET_MARKER, False):
        @wraps(source_packet_current)
        def semantic_source_packet(record: dict[str, Any]) -> dict[str, Any]:
            source = deepcopy(source_packet_current(record))
            source["truth"] = canonical_mid_truth_payload(_dict(source.get("truth")))
            return source

        setattr(semantic_source_packet, _SOURCE_PACKET_MARKER, True)
        setattr(semantic_source_packet, "_nico_previous", source_packet_current)
        mid_review_by_exception._source_packet = semantic_source_packet
        source_packet_installed = True

    current_truth_current: Callable[..., dict[str, Any]] = mid_assessment_approval._current_truth
    current_truth_installed = False
    if not getattr(current_truth_current, _CURRENT_TRUTH_MARKER, False):
        @wraps(current_truth_current)
        def semantic_current_truth(run: dict[str, Any], store: Any) -> dict[str, Any]:
            return canonical_mid_truth_payload(current_truth_current(run, store))

        setattr(semantic_current_truth, _CURRENT_TRUTH_MARKER, True)
        setattr(semantic_current_truth, "_nico_previous", current_truth_current)
        mid_assessment_approval._current_truth = semantic_current_truth
        current_truth_installed = True

    # The approval module imports the report generator by value. Bind it to the
    # current quality-gated generator after all report wrappers are installed.
    mid_assessment_approval.generate_mid_draft_report = mid_assessment_report.generate_mid_draft_report

    approval_current: Callable[..., dict[str, Any]] = mid_assessment_approval.request_mid_approval
    approval_installed = False
    if not getattr(approval_current, _APPROVAL_MARKER, False):
        @wraps(approval_current)
        def semantic_approval_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
            first = approval_current(*args, **kwargs)
            if first.get("status") != "blocked" or not _stale_approval_error(first.get("error")):
                return first
            second = approval_current(*args, **kwargs)
            if second.get("status") == "blocked" and _stale_approval_error(second.get("error")):
                output = deepcopy(second)
                output["code"] = "mid_approval_identity_still_stale"
                output["truth_identity_diagnostics"] = {
                    "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
                    "retry_count": 1,
                    "first_error": str(first.get("error") or "")[:240],
                    "second_error": str(second.get("error") or "")[:240],
                    "duplicate_start_allowed": False,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
                return output
            return second

        setattr(semantic_approval_request, _APPROVAL_MARKER, True)
        setattr(semantic_approval_request, "_nico_previous", approval_current)
        mid_assessment_approval.request_mid_approval = semantic_approval_request
        mid_assessment_api.request_mid_approval = semantic_approval_request
        approval_installed = True

    terminal_current: Callable[[dict[str, Any]], dict[str, Any] | None] = (
        mid_terminal_truth_patch._terminal_retained_response
    )
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
        "status": "installed" if any(
            (
                source_identity_installed,
                source_packet_installed,
                current_truth_installed,
                approval_installed,
                terminal_installed,
            )
        ) else "already_installed",
        "version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
        "lossless_truth_normalization": True,
        "truth_fields_removed": False,
        "unsupported_claims_preserved": True,
        "optional_evidence_changes_identity": True,
        "canonical_truth_before_packet_identity": True,
        "canonical_truth_before_report_identity": True,
        "canonical_truth_before_approval_identity": True,
        "bounded_stale_retry_count": 1,
        "same_run_stale_approval_repair": True,
        "repository_recaptured_during_repair": False,
        "scanner_rerun_during_repair": False,
        "score_recomputed_during_repair": False,
        "replacement_run_created": False,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_TRUTH_IDENTITY_CONSISTENCY_VERSION",
    "canonical_mid_truth_payload",
    "install_mid_truth_identity_consistency",
    "repair_stale_mid_approval",
    "semantic_mid_truth_hash",
]
