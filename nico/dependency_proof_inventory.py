from __future__ import annotations

import hashlib
import json
import math
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
_MAX_HASH_DEPTH = 64


def _hash_key(value: Any) -> str:
    if isinstance(value, str):
        return value
    return f"{type(value).__name__}:{value}"


def _canonical_hash_value(
    value: Any,
    *,
    active_container_ids: set[int] | None = None,
    depth: int = 0,
) -> Any:
    """Convert arbitrary scanner evidence into a deterministic JSON-safe hash shape.

    Scanner integrations are third-party boundaries and may return self-referential
    containers or non-JSON-native values. Hashing must never terminate an assessment
    for those representation details. Circular references and excessive nesting are
    represented explicitly; the original evidence remains untouched.
    """

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"$non_finite_float": str(value)}
    if depth >= _MAX_HASH_DEPTH:
        return {"$truncated": "maximum_hash_depth"}

    active = active_container_ids if active_container_ids is not None else set()
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": "dict"}
        active.add(identity)
        try:
            return {
                _hash_key(key): _canonical_hash_value(item, active_container_ids=active, depth=depth + 1)
                for key, item in value.items()
            }
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": type(value).__name__}
        active.add(identity)
        try:
            return [
                _canonical_hash_value(item, active_container_ids=active, depth=depth + 1)
                for item in value
            ]
        finally:
            active.remove(identity)

    if isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in active:
            return {"$circular_reference": type(value).__name__}
        active.add(identity)
        try:
            normalized = [
                _canonical_hash_value(item, active_container_ids=active, depth=depth + 1)
                for item in value
            ]
        finally:
            active.remove(identity)
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )

    return {
        "$type": f"{type(value).__module__}.{type(value).__qualname__}",
        "$value": str(value),
    }


def stable_json_hash(value: Any) -> str:
    """Return a deterministic SHA-256 hash for arbitrary scanner evidence."""

    encoded = json.dumps(
        _canonical_hash_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_hash(value: Any) -> str:
    """Backward-compatible private alias for existing dependency-proof callers."""

    return stable_json_hash(value)


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
        "artifact_hash": stable_json_hash(payload) if payload else None,
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
    inventory["inventory_hash"] = stable_json_hash({key: value for key, value in inventory.items() if key != "inventory_hash"})
    return inventory


__all__ = [
    "DEPENDENCY_SCANNER_TOOLS",
    "EXPECTED_DEPENDENCY_FILES",
    "SCHEMA",
    "build_dependency_proof_inventory",
    "stable_json_hash",
]
