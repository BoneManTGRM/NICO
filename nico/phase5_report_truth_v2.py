from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico import phase5_report_truth_v1 as base

VERSION = "nico.phase5_report_truth.v2"
_ORIGINAL_NORMALIZED_SCANNER_RECORD = base._normalized_scanner_record
_ORIGINAL_RECONCILE = base.reconcile_phase5_report_truth
_STATUS_ALIASES = {
    "complete": "completed",
    "completed": "completed",
    "success": "completed",
    "passed": "completed",
    "failure": "failed",
    "error": "failed",
    "timed-out": "timeout",
    "timed_out": "timeout",
    "incomplete": "partial",
}


def _find_commit(value: Any) -> str:
    if isinstance(value, dict):
        checkout = value.get("checkout") if isinstance(value.get("checkout"), dict) else {}
        provenance = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
        for candidate in (
            value.get("target_commit_sha"),
            value.get("snapshot_commit_sha"),
            value.get("commit_sha"),
            checkout.get("commit_sha"),
            provenance.get("target_commit_sha"),
        ):
            commit = base._sha(candidate)
            if commit:
                return commit
        for child in value.values():
            commit = _find_commit(child)
            if commit:
                return commit
    elif isinstance(value, list):
        for child in value:
            commit = _find_commit(child)
            if commit:
                return commit
    return ""


def _normalized_scanner_record_v2(
    tool: str,
    payload: dict[str, Any],
    *,
    context: dict[str, str],
    path: str,
    target_commit: str,
) -> dict[str, Any]:
    normalized_payload = dict(payload)
    original_status = str(payload.get("status") or "").strip().casefold()
    normalized_payload["status"] = _STATUS_ALIASES.get(original_status, original_status)

    # Current structured execution records may use `complete` but preserve the
    # underlying canonical proof fields. Never infer proof fields from status alone.
    record = _ORIGINAL_NORMALIZED_SCANNER_RECORD(
        tool,
        normalized_payload,
        context=context,
        path=path,
        target_commit=target_commit,
    )
    record["source_status"] = original_status or "unknown"
    return record


def reconcile_phase5_report_truth(
    assessment: dict[str, Any],
    stage_results: dict[str, Any],
) -> dict[str, Any]:
    target_commit = _find_commit(stage_results)
    if not target_commit:
        return _ORIGINAL_RECONCILE(assessment, stage_results)
    enriched = {"phase5_exact_identity": {"commit_sha": target_commit}, **deepcopy(stage_results)}
    return _ORIGINAL_RECONCILE(assessment, enriched)


def install_phase5_report_truth_v2() -> dict[str, Any]:
    base._normalized_scanner_record = _normalized_scanner_record_v2
    base.reconcile_phase5_report_truth = reconcile_phase5_report_truth
    result = dict(base.install_phase5_report_truth_v1())
    result.update(
        {
            "status": "installed",
            "version": VERSION,
            "scanner_status_aliases_normalized": True,
            "nested_exact_commit_discovery": True,
        }
    )
    return result


BASELINE = base.BASELINE
scan_files_executable_only = base.scan_files_executable_only

__all__ = [
    "VERSION",
    "BASELINE",
    "scan_files_executable_only",
    "reconcile_phase5_report_truth",
    "install_phase5_report_truth_v2",
]
