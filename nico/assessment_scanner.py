from __future__ import annotations

import os
import time
from copy import deepcopy
from typing import Any

from nico.scanner_worker import get_scan, start_scan

DEFAULT_EXPRESS_SCANNER_TOOLS = ["pip-audit", "npm-audit", "osv-scanner", "bandit"]


def _bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _scanner_tools() -> list[str]:
    configured = os.getenv("NICO_EXPRESS_SCANNER_TOOLS", "")
    tools = [item.strip() for item in configured.split(",") if item.strip()]
    return tools or DEFAULT_EXPRESS_SCANNER_TOOLS


def _wait_seconds() -> float:
    try:
        return max(0.0, min(float(os.getenv("NICO_EXPRESS_SCANNER_WAIT_SECONDS", "2.0")), 10.0))
    except ValueError:
        return 2.0


def _authorized_by(payload: dict[str, Any]) -> str:
    value = str(payload.get("authorized_by") or "").strip()
    if value and value.lower() != "unspecified":
        return value
    return "web_user_confirmed_explicit_permission"


def attach_auto_scanner_evidence(result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    if output.get("status") != "complete":
        output["scanner_attachment"] = {"status": "not_started", "reason": "Assessment was not complete."}
        return output
    if not _bool_env("NICO_EXPRESS_AUTO_SCANNER", True):
        output["scanner_attachment"] = {"status": "disabled", "reason": "NICO_EXPRESS_AUTO_SCANNER is disabled."}
        return output
    if not request.get("authorized"):
        output["scanner_attachment"] = {"status": "blocked", "reason": "Scanner attachment requires explicit authorization."}
        return output

    scan_payload = {
        "repository": request.get("repository"),
        "authorized": True,
        "customer_id": request.get("customer_id") or "default_customer",
        "project_id": request.get("project_id") or "default_project",
        "authorized_by": _authorized_by(request),
        "authorization_scope": request.get("authorization_scope") or "Express assessment scanner evidence; defensive read-only repository review.",
        "draft_pr_creation_allowed": False,
        "tools": _scanner_tools(),
    }
    queued = start_scan(scan_payload)
    if queued.get("status") == "blocked":
        output["scanner_attachment"] = {"status": "blocked", "reason": queued.get("error") or "Scanner worker rejected the request."}
        output.setdefault("unavailable_data_notes", []).append("Automatic scanner attachment was blocked; no scanner-clean claim is made.")
        return output

    scan_id = queued.get("scan_id")
    deadline = time.monotonic() + _wait_seconds()
    scan = queued
    while scan_id and time.monotonic() < deadline:
        scan = get_scan(scan_id)
        if scan.get("status") in {"complete", "failed", "blocked"}:
            break
        time.sleep(0.2)

    output["scanner_run"] = scan
    output["scanner_attachment"] = {
        "status": scan.get("status", "queued"),
        "scan_id": scan_id,
        "tools_requested": scan_payload["tools"],
        "mode": "automatic_express_attachment",
        "human_review_required": True,
    }
    if scan.get("scanner_results"):
        output["scanner_results"] = scan.get("scanner_results", [])
        output.setdefault("evidence_readiness", {})["automatic_scanner_attached"] = True
    else:
        output.setdefault("unavailable_data_notes", []).append("Automatic scanner worker was queued but completed scanner evidence was not available before the Express response returned. Refresh scanner status before scanner-backed claims.")
    return output
