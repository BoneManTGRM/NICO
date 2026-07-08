from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

DEFAULT_TOOL_TIMEOUT_SECONDS = int(os.getenv("NICO_TOOL_TIMEOUT_SECONDS", "45"))
TOTAL_SCAN_TIMEOUT_SECONDS = int(os.getenv("NICO_TOTAL_SCAN_TIMEOUT_SECONDS", "300"))
MAX_OUTPUT_CHARS = int(os.getenv("NICO_MAX_TOOL_OUTPUT", "12000"))
MAX_REPO_BYTES = int(os.getenv("NICO_MAX_REPO_BYTES", "150000000"))

SCANNER_JOB_STATUSES = ("blocked", "queued", "running", "completed", "failed")
SAFE_TIMEOUT_CONFIG = {
    "tool_timeout_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS,
    "total_scan_timeout_seconds": TOTAL_SCAN_TIMEOUT_SECONDS,
    "max_output_chars": MAX_OUTPUT_CHARS,
    "max_repo_bytes": MAX_REPO_BYTES,
}

TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "bandit": {"intent": "Python static review", "tier": "static"},
    "semgrep": {"intent": "static review", "tier": "static"},
    "eslint": {"intent": "JavaScript lint review", "tier": "static"},
    "typescript": {"intent": "TypeScript review", "tier": "static"},
    "pip-audit": {"intent": "Python dependency review", "tier": "dependency"},
    "npm-audit": {"intent": "Node dependency review", "tier": "dependency"},
    "pytest": {"intent": "Python test review", "tier": "test"},
    "npm-test": {"intent": "Node test review", "tier": "test"},
    "npm-build": {"intent": "Node build review", "tier": "build"},
}

ALLOWED_SCANNER_COMMANDS: dict[str, str] = {name: cfg["intent"] for name, cfg in TOOL_CATALOG.items()}

ARTIFACT_RESULT_SCHEMA = {
    "scanner": "scanner name",
    "status": "unavailable|parsed|passed|failed|error",
    "available": False,
    "artifact_path": "optional artifact path",
    "summary": "human readable evidence summary",
    "finding_count": 0,
    "severity_counts": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
    "blocking_finding_count": 0,
    "unavailable_data_notes": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_repo_url(repository: str) -> str:
    value = (repository or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        return f"https://github.com/{value}.git"
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc.lower() == "github.com" and parsed.path.count("/") >= 2:
        path = parsed.path.rstrip("/")
        return value if path.endswith(".git") else f"https://github.com{path}.git"
    raise ValueError("repository must be owner/name or an https://github.com/owner/repo URL")


def validate_requested_tools(requested_tools: list[str] | None) -> tuple[list[str], list[str]]:
    requested = [str(item).strip() for item in (requested_tools or []) if str(item).strip()]
    if not requested:
        return list(TOOL_CATALOG.keys()), []
    allowed = set(TOOL_CATALOG)
    valid = [item for item in requested if item in allowed]
    invalid = [item for item in requested if item not in allowed]
    return valid, invalid


def scanner_job_model(payload: dict[str, Any], scan_id: str | None = None) -> dict[str, Any]:
    tools, invalid_tools = validate_requested_tools(payload.get("tools") or [])
    return {
        "scan_id": scan_id or f"scan_{uuid4().hex[:16]}",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "repository": payload.get("repository") or "",
        "authorized": bool(payload.get("authorized")),
        "authorized_by": payload.get("authorized_by") or "",
        "authorization_scope": payload.get("authorization_scope") or "",
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "tools_requested": tools,
        "invalid_tools": invalid_tools,
        "allowed_scanner_commands": {name: ALLOWED_SCANNER_COMMANDS[name] for name in tools},
        "safe_timeout_config": dict(SAFE_TIMEOUT_CONFIG),
        "artifact_result_schema": dict(ARTIFACT_RESULT_SCHEMA),
        "execution_started": False,
        "scanner_results": [],
        "unavailable_tools": [],
        "human_review_required": True,
        "code_modification_allowed": False,
        "rule": "This foundation model only validates authorization, tool names, timeouts, and artifact shape. It does not run repository tools.",
    }


def validate_scanner_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required."}
    if not payload.get("repository"):
        return {"status": "blocked", "error": "repository is required."}
    if not str(payload.get("authorized_by") or "").strip() or str(payload.get("authorized_by")).strip().lower() == "unspecified":
        return {"status": "blocked", "error": "authorized_by is required."}
    if not str(payload.get("authorization_scope") or "").strip():
        return {"status": "blocked", "error": "authorization_scope is required."}
    try:
        safe_repo_url(payload.get("repository", ""))
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}
    _valid, invalid = validate_requested_tools(payload.get("tools") or [])
    if invalid:
        return {"status": "blocked", "error": "Requested scanner tool is not allowlisted.", "invalid_tools": invalid, "allowed_tools": sorted(TOOL_CATALOG)}
    return {"status": "ok"}


def missing_artifact_result(scanner: str, reason: str = "artifact_not_provided") -> dict[str, Any]:
    return {
        "scanner": scanner,
        "status": "unavailable",
        "available": False,
        "artifact_path": "",
        "summary": f"{scanner} artifact was not provided; scanner is not marked available.",
        "finding_count": 0,
        "severity_counts": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
        "blocking_finding_count": 0,
        "unavailable_data_notes": [reason],
    }
