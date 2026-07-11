from __future__ import annotations

from typing import Any

from nico.full_assessment_orchestrator import default_full_assessment_handlers
from nico.repository_snapshot import capture_repository_snapshot
from nico.scanner_worker import get_scan
from nico.snapshot_scanner_worker import start_snapshot_scan


def _snapshot_repository_handler(context: dict[str, Any], _outputs: dict[str, Any]) -> dict[str, Any]:
    snapshot = capture_repository_snapshot(context)
    if snapshot.get("status") != "attached":
        return {
            "status": "blocked",
            "message": "The exact repository commit snapshot could not be captured; deep assessment execution was blocked.",
            "repository_snapshot": snapshot,
            "evidence": {
                "run_id": context.get("run_id") or "",
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_status": snapshot.get("status") or "unavailable",
                "unavailable_data_notes": snapshot.get("unavailable_data_notes") or [],
            },
        }
    return {
        "status": "complete",
        "message": "The exact default-branch commit was captured and bound to this assessment run.",
        "repository_snapshot": snapshot,
        "evidence": {
            "run_id": context.get("run_id") or "",
            "repository": context.get("repository") or "",
            "snapshot_id": snapshot.get("snapshot_id") or "",
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
            "snapshot_tree_sha": snapshot.get("tree_sha") or "",
            "default_branch": snapshot.get("default_branch") or "",
            "idempotent_reuse": bool(snapshot.get("idempotent_reuse")),
        },
    }


def _snapshot_from_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    repo_step = outputs.get("repo_evidence") if isinstance(outputs.get("repo_evidence"), dict) else {}
    return repo_step.get("repository_snapshot") if isinstance(repo_step.get("repository_snapshot"), dict) else {}


def _scan_matches_snapshot(scan: dict[str, Any], snapshot: dict[str, Any], run_id: str) -> bool:
    return bool(
        str(scan.get("run_id") or "") == str(run_id or "")
        and str(scan.get("snapshot_id") or "") == str(snapshot.get("snapshot_id") or "")
        and str(scan.get("snapshot_commit_sha") or "").lower() == str(snapshot.get("commit_sha") or "").lower()
    )


def _snapshot_scanner_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot_from_outputs(outputs)
    if snapshot.get("status") != "attached":
        return {
            "status": "blocked",
            "message": "Scanner execution requires an attached repository snapshot.",
            "evidence": {"run_id": context.get("run_id") or "", "snapshot_status": snapshot.get("status") or "missing"},
        }

    if context.get("scan_id"):
        scan = get_scan(str(context["scan_id"]))
        if scan.get("status") == "not_found":
            return {
                "status": "unavailable",
                "message": "Requested snapshot-bound scanner run was not found.",
                "scan": scan,
                "evidence": {"run_id": context["run_id"], "scan_id": context["scan_id"], "snapshot_id": snapshot.get("snapshot_id")},
            }
        if not _scan_matches_snapshot(scan, snapshot, context["run_id"]):
            return {
                "status": "blocked",
                "message": "Scanner identity does not match the run and repository snapshot; evidence attachment was blocked.",
                "scan": scan,
                "evidence": {
                    "run_id": context["run_id"],
                    "scan_id": context["scan_id"],
                    "snapshot_id": snapshot.get("snapshot_id"),
                    "snapshot_commit_sha": snapshot.get("commit_sha"),
                    "scanner_run_id": scan.get("run_id"),
                    "scanner_snapshot_id": scan.get("snapshot_id"),
                    "scanner_snapshot_commit_sha": scan.get("snapshot_commit_sha"),
                },
            }
        return {
            "status": scan.get("status") or "unknown",
            "message": "Existing scanner run was loaded and matched to the exact assessment snapshot.",
            "scan": scan,
            "evidence": {
                "run_id": context["run_id"],
                "scan_id": scan.get("scan_id") or "",
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_commit_sha": snapshot.get("commit_sha") or "",
                "actual_commit_sha": scan.get("actual_commit_sha") or "",
                "snapshot_match": bool(scan.get("snapshot_match")),
            },
        }

    if not context.get("run_scanners"):
        return {
            "status": "skipped",
            "message": "Snapshot-bound scanner execution was skipped by request; scanner-backed conclusions remain unavailable.",
            "evidence": {
                "run_id": context["run_id"],
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_commit_sha": snapshot.get("commit_sha") or "",
            },
        }

    scan = start_snapshot_scan(
        {
            "repository": context["repository"],
            "authorized": True,
            "customer_id": context["customer_id"],
            "project_id": context["project_id"],
            "run_id": context["run_id"],
            "authorized_by": context["authorized_by"],
            "authorization_scope": context["authorization_scope"],
            "snapshot_id": snapshot.get("snapshot_id") or "",
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
            "tools": context.get("tools") or [],
        }
    )
    if scan.get("status") == "blocked":
        return {
            "status": "blocked",
            "message": "Snapshot-bound scanner execution was blocked.",
            "scan": scan,
            "evidence": {
                "run_id": context["run_id"],
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_commit_sha": snapshot.get("commit_sha") or "",
            },
        }
    return {
        "status": scan.get("status") or "queued",
        "message": "Snapshot-bound scanner execution was queued for the exact captured commit.",
        "scan": scan,
        "evidence": {
            "run_id": context["run_id"],
            "scan_id": scan.get("scan_id") or "",
            "snapshot_id": snapshot.get("snapshot_id") or "",
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
            "tools_requested": scan.get("tools_requested") or [],
        },
    }


def _snapshot_evidence_attachment_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    scanner_step = outputs.get("scanner_worker") if isinstance(outputs.get("scanner_worker"), dict) else {}
    scan = scanner_step.get("scan") if isinstance(scanner_step.get("scan"), dict) else {}
    snapshot = _snapshot_from_outputs(outputs)
    scan_id = str(scan.get("scan_id") or context.get("scan_id") or "")
    if not scan_id:
        return {
            "status": "skipped",
            "message": "No snapshot-bound scanner run exists, so scanner evidence remains unavailable.",
            "evidence": {"run_id": context["run_id"], "snapshot_id": snapshot.get("snapshot_id") or "", "scan_id": ""},
        }
    if scanner_step.get("status") in {"blocked", "failed", "unavailable"}:
        return {
            "status": scanner_step.get("status"),
            "message": "Snapshot-bound scanner evidence could not be attached.",
            "evidence": {
                "run_id": context["run_id"],
                "scan_id": scan_id,
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "scanner_status": scanner_step.get("status"),
            },
        }
    if scan.get("status") in {"queued", "running"}:
        return {
            "status": "pending",
            "message": "Snapshot-bound scanner execution is still running.",
            "evidence": {
                "run_id": context["run_id"],
                "scan_id": scan_id,
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_commit_sha": snapshot.get("commit_sha") or "",
                "scanner_status": scan.get("status"),
            },
        }
    if scan.get("status") != "complete" or not scan.get("snapshot_match"):
        return {
            "status": "unavailable",
            "message": "Scanner output did not prove execution against the captured snapshot and was not attached as completed evidence.",
            "evidence": {
                "run_id": context["run_id"],
                "scan_id": scan_id,
                "snapshot_id": snapshot.get("snapshot_id") or "",
                "snapshot_commit_sha": snapshot.get("commit_sha") or "",
                "actual_commit_sha": scan.get("actual_commit_sha") or "",
                "snapshot_match": bool(scan.get("snapshot_match")),
                "scanner_status": scan.get("status") or "unknown",
            },
        }

    results = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    evidence = {
        "status": "attached",
        "run_id": context["run_id"],
        "scan_id": scan_id,
        "snapshot_id": snapshot.get("snapshot_id") or "",
        "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        "actual_commit_sha": scan.get("actual_commit_sha") or "",
        "snapshot_match": True,
        "scanner_status": "complete",
        "tools_requested": scan.get("tools_requested") or [],
        "tools_run": scan.get("tools_run") or [],
        "unavailable_tools": scan.get("unavailable_tools") or [],
        "failed_tools": scan.get("failed_tools") or [],
        "timed_out_tools": scan.get("timed_out_tools") or [],
        "scanner_results_count": len(results),
        "evidence_summary": scan.get("evidence_summary") if isinstance(scan.get("evidence_summary"), dict) else {},
        "unavailable_data_notes": scan.get("unavailable_data_notes") or [],
        "secret_redaction_applied": bool(scan.get("secret_redaction_applied")),
        "retention_note": scan.get("retention_note") or "Snapshot-bound scanner evidence was loaded from the retained scanner record.",
        "human_review_required": True,
    }
    return {
        "status": "complete",
        "message": "Completed scanner evidence was attached only after run ID and exact commit snapshot verification.",
        "scanner_evidence": evidence,
        "evidence": evidence,
    }


def snapshot_bound_assessment_handlers() -> dict[str, Any]:
    handlers = default_full_assessment_handlers()
    handlers["repo_evidence"] = _snapshot_repository_handler
    handlers["scanner_worker"] = _snapshot_scanner_handler
    handlers["evidence_attachment"] = _snapshot_evidence_attachment_handler
    return handlers
