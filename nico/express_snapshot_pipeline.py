from __future__ import annotations

import os
import time
from copy import deepcopy
from typing import Any, Callable

from fastapi import HTTPException

from nico.repository_snapshot import capture_repository_snapshot
from nico.scanner_worker import get_scan
from nico.snapshot_scanner_worker import start_snapshot_scan

EXPRESS_SNAPSHOT_PIPELINE_VERSION = "nico.express_snapshot_pipeline.v1"
_TERMINAL_SCANNER_STATES = {
    "complete",
    "unavailable",
    "failed",
    "error",
    "blocked",
    "cancelled",
    "interrupted",
    "recovery_required",
}


def _wait_seconds() -> int:
    try:
        configured = int(os.getenv("NICO_EXPRESS_SCANNER_WAIT_SECONDS", "0"))
    except (TypeError, ValueError):
        configured = 0
    if configured > 0:
        return max(60, min(configured, 3600))
    try:
        scanner_budget = int(os.getenv("NICO_TOTAL_SCAN_TIMEOUT_SECONDS", "1500"))
    except (TypeError, ValueError):
        scanner_budget = 1500
    return max(300, min(scanner_budget + 180, 3600))


def _safe_scan(scan: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "scan_id",
        "run_id",
        "repository",
        "customer_id",
        "project_id",
        "status",
        "current_stage",
        "progress_percent",
        "active_tool",
        "tools_requested",
        "tools_run",
        "unavailable_tools",
        "failed_tools",
        "timed_out_tools",
        "full_history_verified_tools",
        "snapshot_id",
        "snapshot_commit_sha",
        "actual_commit_sha",
        "snapshot_match",
        "heartbeat_at",
        "heartbeat_sequence",
        "heartbeat_process_id",
        "heartbeat_thread",
        "heartbeat_persistence_status",
        "heartbeat_failure_type",
        "tool_elapsed_seconds",
        "duration_seconds",
        "finding_count",
        "material_finding_count",
        "review_required_finding_count",
        "excluded_test_only_finding_count",
        "finding_summary",
        "evidence_summary",
        "unavailable_data_notes",
        "secret_redaction_applied",
        "redaction_policy_applied",
        "retention_note",
        "created_at",
        "updated_at",
        "completed_at",
        "scanner_results",
        "recovery",
    )
    return {key: deepcopy(scan.get(key)) for key in allowed if key in scan}


def _snapshot_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(snapshot.get("commit_sha") or ""),
        "snapshot_tree_sha": str(snapshot.get("tree_sha") or ""),
        "default_branch": str(snapshot.get("default_branch") or ""),
        "snapshot_captured_at": str(snapshot.get("captured_at") or ""),
    }


def _failure(
    status_code: int,
    code: str,
    message: str,
    *,
    run_id: str,
    snapshot: dict[str, Any] | None = None,
    scan: dict[str, Any] | None = None,
    recovery_required: bool = False,
) -> HTTPException:
    safe_scan = _safe_scan(scan or {})
    detail: dict[str, Any] = {
        "status": "interrupted" if recovery_required else "blocked" if status_code < 500 else "failed",
        "code": code,
        "message": message,
        "run_id": run_id,
        "assessment_type": "express",
        "scan_id": safe_scan.get("scan_id") or "",
        "scanner": safe_scan,
        "repository_snapshot": deepcopy(snapshot or {}),
        "recovery_required": recovery_required,
        "recovery_path": "/operations/recovery" if recovery_required else "",
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_ready": False,
    }
    return HTTPException(status_code=status_code, detail=detail)


def start_express_snapshot_scan(
    run_id: str,
    request_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    context = {
        "run_id": run_id,
        "repository": str(request_payload.get("repository") or ""),
        "customer_id": str(request_payload.get("customer_id") or "default_customer"),
        "project_id": str(request_payload.get("project_id") or "default_project"),
    }
    snapshot = capture_repository_snapshot(context)
    if snapshot.get("status") != "attached":
        raise _failure(
            400,
            "express_repository_snapshot_unavailable",
            "Express scanner execution was blocked because NICO could not capture the exact repository commit. No report was generated.",
            run_id=run_id,
            snapshot=snapshot,
        )

    scan = start_snapshot_scan(
        {
            "repository": context["repository"],
            "authorized": True,
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "run_id": run_id,
            "authorized_by": str(request_payload.get("authorized_by") or "requester_confirmation"),
            "authorization_scope": str(request_payload.get("authorization_scope") or "repository assessment only"),
            "snapshot_id": str(snapshot.get("snapshot_id") or ""),
            "snapshot_commit_sha": str(snapshot.get("commit_sha") or ""),
            "tools": request_payload.get("tools") if isinstance(request_payload.get("tools"), list) else [],
        }
    )
    if scan.get("status") == "blocked" or not scan.get("scan_id"):
        raise _failure(
            400,
            "express_snapshot_scanner_blocked",
            "Express scanner execution was blocked before a scanner run could be created. No report was generated.",
            run_id=run_id,
            snapshot=snapshot,
            scan=scan,
        )
    return snapshot, _safe_scan(scan)


def _identity_matches(scan: dict[str, Any], snapshot: dict[str, Any], run_id: str) -> bool:
    return bool(
        str(scan.get("run_id") or "") == run_id
        and str(scan.get("snapshot_id") or "") == str(snapshot.get("snapshot_id") or "")
        and str(scan.get("snapshot_commit_sha") or "").lower() == str(snapshot.get("commit_sha") or "").lower()
    )


def wait_for_express_snapshot_scan(
    run_id: str,
    snapshot: dict[str, Any],
    initial_scan: dict[str, Any],
    *,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    scan_id = str(initial_scan.get("scan_id") or "")
    deadline = time.monotonic() + _wait_seconds()
    last_signature: tuple[Any, ...] | None = None

    while True:
        scan = _safe_scan(get_scan(scan_id))
        if scan.get("status") == "not_found":
            raise _failure(
                503,
                "express_snapshot_scanner_missing",
                "The exact Express scanner record could not be read. The run remains preserved for Recovery and no report was generated.",
                run_id=run_id,
                snapshot=snapshot,
                scan=scan,
                recovery_required=True,
            )
        if not _identity_matches(scan, snapshot, run_id):
            raise _failure(
                400,
                "express_snapshot_scanner_identity_mismatch",
                "The scanner identity did not match the exact Express run and repository snapshot. NICO blocked report generation.",
                run_id=run_id,
                snapshot=snapshot,
                scan=scan,
            )

        signature = (
            scan.get("status"),
            scan.get("current_stage"),
            scan.get("progress_percent"),
            scan.get("active_tool"),
            scan.get("heartbeat_sequence"),
        )
        if signature != last_signature and on_update is not None:
            on_update(deepcopy(scan))
            last_signature = signature

        status = str(scan.get("status") or "unknown").lower()
        if status in _TERMINAL_SCANNER_STATES:
            if status == "complete" and bool(scan.get("snapshot_match")):
                return scan
            raise _failure(
                503,
                "express_snapshot_scanner_incomplete",
                "The Express scanner reached a terminal state without verified completion against the captured commit. NICO did not generate a report.",
                run_id=run_id,
                snapshot=snapshot,
                scan=scan,
                recovery_required=status in {"interrupted", "recovery_required"},
            )

        if time.monotonic() >= deadline:
            raise _failure(
                503,
                "express_snapshot_scanner_wait_timeout",
                "The Express scanner exceeded the bounded wait window. The exact scanner remains preserved for Recovery and no report was generated.",
                run_id=run_id,
                snapshot=snapshot,
                scan=scan,
                recovery_required=True,
            )
        time.sleep(1.0)


def _remove_obsolete_scanner_limitations(output: dict[str, Any]) -> None:
    markers = (
        "pip-audit, npm audit, and osv scanner cli execution are not yet run",
        "semgrep, bandit, eslint, and typescript checks are not yet executed",
        "full git-history secret scanning requires a sandboxed worker",
        "cli scanners are marked unavailable until",
        "add a sandboxed worker that checks out authorized repositories",
        "add scanner-worker execution for",
    )

    def retained(items: Any) -> list[Any]:
        if not isinstance(items, list):
            return []
        return [item for item in items if not any(marker in str(item).lower() for marker in markers)]

    for key in ("unavailable_data_notes", "medium_term_plan", "risk_register", "repairs"):
        if key in output:
            output[key] = retained(output.get(key))
    for section in output.get("sections") or []:
        if isinstance(section, dict):
            section["unavailable"] = retained(section.get("unavailable"))


def _apply_scanner_to_core_sections(output: dict[str, Any], scan: dict[str, Any], snapshot: dict[str, Any]) -> None:
    sections = [item for item in output.get("sections") or [] if isinstance(item, dict)]
    by_id = {str(item.get("id") or ""): item for item in sections}
    category_sections = {
        "dependency": "dependency_health",
        "static": "static_analysis",
        "secret": "secrets_review",
        "coverage": "code_audit",
    }
    source_map = {
        "dependency": "dependency_intelligence",
        "static": "static_analysis",
        "secret": "secret_scanning",
        "coverage": "test_execution",
    }
    commit = str(snapshot.get("commit_sha") or "")
    for result in scan.get("scanner_results") or []:
        if not isinstance(result, dict):
            continue
        category = str(result.get("category") or "")
        section = by_id.get(category_sections.get(category, ""))
        if section is None:
            continue
        tool = str(result.get("tool") or result.get("scanner") or "scanner")
        status = str(result.get("status") or "unknown").lower()
        findings = [item for item in result.get("findings") or [] if isinstance(item, dict)]
        section.setdefault("evidence", [])
        section.setdefault("findings", [])
        section.setdefault("unavailable", [])
        sources = set(section.get("evidence_sources") or [])
        sources.add(source_map.get(category, "scanner_worker"))
        section["evidence_sources"] = sorted(sources)
        note = (
            f"Exact-snapshot {tool} status={status}; findings={len(findings)}; "
            f"commit={commit[:12]}; scan_id={scan.get('scan_id')}."
        )
        if status == "completed":
            if note not in section["evidence"]:
                section["evidence"].append(note)
            if findings:
                finding_note = f"{tool} returned {len(findings)} finding(s) requiring human triage."
                if finding_note not in section["findings"]:
                    section["findings"].append(finding_note)
        elif status == "unavailable":
            unavailable_note = f"{tool} was unavailable in the exact-snapshot scanner: {str(result.get('reason') or 'tool unavailable')[:240]}"
            if unavailable_note not in section["unavailable"]:
                section["unavailable"].append(unavailable_note)
        else:
            finding_note = f"{tool} ended with status {status}; its output requires human review before client-facing conclusions."
            if finding_note not in section["findings"]:
                section["findings"].append(finding_note)
    output["sections"] = sections


def attach_exact_express_scanner_evidence(
    result: dict[str, Any],
    snapshot: dict[str, Any],
    scan: dict[str, Any],
) -> dict[str, Any]:
    output = deepcopy(result)
    safe_scan = _safe_scan(scan)
    output["repository_snapshot"] = deepcopy(snapshot)
    output.update(_snapshot_evidence(snapshot))
    output["scan_id"] = str(safe_scan.get("scan_id") or "")
    output["scanner"] = safe_scan
    output["scanner_run"] = safe_scan
    output["scanner_results"] = deepcopy(safe_scan.get("scanner_results") or [])
    output["worker_evidence_attachment"] = {
        "status": "complete",
        "mode": "exact_same_run_snapshot_bound",
        "run_id": str(safe_scan.get("run_id") or ""),
        "scan_id": str(safe_scan.get("scan_id") or ""),
        "snapshot_id": str(safe_scan.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(safe_scan.get("snapshot_commit_sha") or ""),
        "actual_commit_sha": str(safe_scan.get("actual_commit_sha") or ""),
        "snapshot_match": bool(safe_scan.get("snapshot_match")),
        "tools_requested": deepcopy(safe_scan.get("tools_requested") or []),
        "tools_run": deepcopy(safe_scan.get("tools_run") or []),
        "unavailable_tools": deepcopy(safe_scan.get("unavailable_tools") or []),
        "failed_tools": deepcopy(safe_scan.get("failed_tools") or []),
        "timed_out_tools": deepcopy(safe_scan.get("timed_out_tools") or []),
        "finding_summary": deepcopy(safe_scan.get("finding_summary") or {}),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    readiness = output.get("evidence_readiness") if isinstance(output.get("evidence_readiness"), dict) else {}
    readiness.update(
        {
            "scanner_worker_attached": True,
            "exact_snapshot_scanner_completed": True,
            "same_run_scanner_identity_verified": True,
            "snapshot_match": True,
        }
    )
    output["evidence_readiness"] = readiness
    _remove_obsolete_scanner_limitations(output)
    _apply_scanner_to_core_sections(output, safe_scan, snapshot)
    return output


__all__ = [
    "EXPRESS_SNAPSHOT_PIPELINE_VERSION",
    "attach_exact_express_scanner_evidence",
    "start_express_snapshot_scan",
    "wait_for_express_snapshot_scan",
]
