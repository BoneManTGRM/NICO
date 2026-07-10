from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "nico.dependency_proof_inventory.v1"
EXPECTED_DEPENDENCY_FILES = (
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "apps/web/package.json",
    "apps/web/package-lock.json",
)
DEPENDENCY_SCANNER_TOOLS = ("pip-audit", "npm-audit", "osv-scanner")


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_row(root: Path, relative_path: str) -> dict[str, Any]:
    path = root / relative_path
    row: dict[str, Any] = {
        "path": relative_path,
        "exists": path.exists() and path.is_file(),
    }
    if row["exists"]:
        raw = path.read_bytes()
        row.update(
            {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return row


def _scanner_row(tool_name: str, tools: dict[str, Any]) -> dict[str, Any]:
    payload = tools.get(tool_name) if isinstance(tools.get(tool_name), dict) else {}
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    status = str(payload.get("status") or "missing")
    row = {
        "tool": tool_name,
        "status": status,
        "exit_code": payload.get("returncode"),
        "timed_out": bool(payload.get("timed_out")),
        "finding_count": len(findings),
        "artifact_hash": _json_hash(payload) if payload else None,
    }
    if payload.get("reason"):
        row["reason"] = payload.get("reason")
    if payload.get("execution_source"):
        row["execution_source"] = payload.get("execution_source")
    return row


def build_dependency_proof_inventory(repo_dir: Path, tools: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create dependency proof over root and apps/web dependency files plus scanner results."""
    tools = tools or {}
    files = [_file_row(repo_dir, relative_path) for relative_path in EXPECTED_DEPENDENCY_FILES]
    scanners = [_scanner_row(tool, tools) for tool in DEPENDENCY_SCANNER_TOOLS]
    existing_paths = [item["path"] for item in files if item["exists"]]
    missing_paths = [item["path"] for item in files if not item["exists"]]
    completed_scanners = [item["tool"] for item in scanners if item["status"] == "completed"]
    unavailable_scanners = [item["tool"] for item in scanners if item["status"] in {"missing", "unavailable", "timeout"}]
    finding_scanners = [item["tool"] for item in scanners if item["finding_count"]]
    inventory = {
        "artifact_schema": SCHEMA,
        "expected_files": list(EXPECTED_DEPENDENCY_FILES),
        "files": files,
        "existing_files": existing_paths,
        "missing_files": missing_paths,
        "scanner_tools": scanners,
        "completed_scanners": completed_scanners,
        "unavailable_scanners": unavailable_scanners,
        "finding_scanners": finding_scanners,
        "current_run_evidence_complete": all(item["status"] == "completed" for item in scanners),
        "guardrail": "Dependency proof requires current-run scanner artifacts and hashes for expected dependency files. Missing files, unavailable scanners, and findings remain explicit.",
    }
    inventory["inventory_hash"] = _json_hash({key: value for key, value in inventory.items() if key != "inventory_hash"})
    return inventory
