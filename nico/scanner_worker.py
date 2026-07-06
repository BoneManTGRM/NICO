from __future__ import annotations

import os
import shutil
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.storage import STORE


TOOL_CATALOG = {
    "pip-audit": {"binary": "pip-audit", "purpose": "Python dependency review"},
    "npm-audit": {"binary": "npm", "purpose": "Node dependency review"},
    "osv-scanner": {"binary": "osv-scanner", "purpose": "OSV dependency review"},
    "semgrep": {"binary": "semgrep", "purpose": "static analysis"},
    "bandit": {"binary": "bandit", "purpose": "Python linting"},
    "eslint": {"binary": "eslint", "purpose": "JavaScript and TypeScript linting"},
    "pytest": {"binary": "pytest", "purpose": "Python test run"},
    "npm-test": {"binary": "npm", "purpose": "Node test run"},
    "npm-build": {"binary": "npm", "purpose": "Node production build"},
}

MAX_OUTPUT_CHARS = int(os.getenv("NICO_MAX_TOOL_OUTPUT", "12000"))
DEFAULT_TOOL_TIMEOUT_SECONDS = int(os.getenv("NICO_TOOL_TIMEOUT_SECONDS", "45"))
TOTAL_SCAN_TIMEOUT_SECONDS = int(os.getenv("NICO_TOTAL_SCAN_TIMEOUT_SECONDS", "300"))
MAX_REPO_BYTES = int(os.getenv("NICO_MAX_REPO_BYTES", "150000000"))
SCAN_JOBS: dict[str, dict[str, Any]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def selected_tools(requested_tools: list[str] | None) -> dict[str, dict[str, str]]:
    if not requested_tools:
        return TOOL_CATALOG
    selected = {name: cfg for name, cfg in TOOL_CATALOG.items() if name in requested_tools}
    return selected or TOOL_CATALOG


def tool_result(name: str, cfg: dict[str, str]) -> dict[str, Any]:
    available = shutil.which(cfg["binary"]) is not None
    return {
        "scanner": name,
        "binary": cfg["binary"],
        "purpose": cfg["purpose"],
        "status": "queued" if available else "unavailable",
        "evidence_summary": f"{name} availability checked in worker environment.",
        "risk_severity": "unknown",
        "recommended_repair": "Enable sandbox execution only after timeout, output, retention, and review controls are verified.",
        "unavailable_data_notes": [] if available else [f"{name} unavailable."],
    }


def _run_scan(scan_id: str, payload: dict[str, Any]) -> None:
    customer_id = payload.get("customer_id") or "default_customer"
    project_id = payload.get("project_id") or "default_project"
    SCAN_JOBS[scan_id]["status"] = "running"
    SCAN_JOBS[scan_id]["updated_at"] = now_iso()
    STORE.put("scanner_runs", scan_id, SCAN_JOBS[scan_id])

    results = [tool_result(name, cfg) for name, cfg in selected_tools(payload.get("tools") or []).items()]
    unavailable = [item for item in results if item["status"] == "unavailable"]
    SCAN_JOBS[scan_id].update({
        "status": "complete",
        "updated_at": now_iso(),
        "completed_at": now_iso(),
        "scanner_results": results,
        "evidence_summary": {
            "mode": "safe_worker_mvp",
            "repository": payload.get("repository"),
            "tools_checked": len(results),
            "unavailable_tools": len(unavailable),
            "note": "This MVP records scanner availability and safety controls. Full command execution remains unavailable until sandbox execution is enabled.",
        },
        "retention_note": "No repository was cloned by this safe MVP worker run.",
    })
    STORE.put("scanner_runs", scan_id, SCAN_JOBS[scan_id])
    STORE.audit("scanner.completed", {"scan_id": scan_id, "status": "complete"}, customer_id=customer_id, project_id=project_id)


def start_scan(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required before scanner worker runs."}
    if not payload.get("repository"):
        return {"status": "blocked", "error": "repository is required."}
    scan_id = f"scan_{uuid4().hex[:16]}"
    job = {
        "scan_id": scan_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": payload.get("repository"),
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "authorized_by": payload.get("authorized_by") or "unspecified",
        "authorization_scope": payload.get("authorization_scope") or "repository assessment only",
        "code_modification_allowed": False,
        "draft_pr_creation_allowed": bool(payload.get("draft_pr_creation_allowed", False)),
        "max_repo_bytes": MAX_REPO_BYTES,
        "tool_timeout_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS,
        "total_scan_timeout_seconds": TOTAL_SCAN_TIMEOUT_SECONDS,
        "max_output_chars": MAX_OUTPUT_CHARS,
    }
    SCAN_JOBS[scan_id] = job
    STORE.put("scanner_runs", scan_id, job)
    STORE.audit("scanner.queued", {"scan_id": scan_id, "repository": payload.get("repository")}, customer_id=job["customer_id"], project_id=job["project_id"])
    threading.Thread(target=_run_scan, args=(scan_id, dict(payload)), daemon=True).start()
    return job


def get_scan(scan_id: str) -> dict[str, Any]:
    return SCAN_JOBS.get(scan_id) or STORE.get("scanner_runs", scan_id) or {"status": "not_found", "scan_id": scan_id}
