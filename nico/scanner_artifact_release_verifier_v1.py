from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Sequence

VERSION = "nico.scanner_artifact_release_verifier.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_scanner_release_evidence(
    records: Sequence[Mapping],
    *,
    assessed_revision: str,
    required_tools: Sequence[str],
) -> dict:
    if not assessed_revision.strip():
        raise RuntimeError("Assessed revision is required")

    by_tool = {str(item.get("tool")): item for item in records}
    failures: list[str] = []
    normalized: list[dict] = []

    for tool in required_tools:
        item = by_tool.get(tool)
        if item is None:
            failures.append(f"{tool}:missing_record")
            continue
        if item.get("status") != "complete":
            failures.append(f"{tool}:status={item.get('status')}")
        if item.get("commit_sha") != assessed_revision:
            failures.append(f"{tool}:revision_mismatch")
        artifact = Path(str(item.get("artifact_path") or ""))
        if not artifact.is_file() or artifact.stat().st_size <= 0:
            failures.append(f"{tool}:artifact_missing")
            continue
        actual_hash = _sha256(artifact)
        expected_hash = str(item.get("artifact_sha256") or "")
        if not expected_hash or actual_hash != expected_hash:
            failures.append(f"{tool}:artifact_hash_mismatch")
        if item.get("exit_code") is None:
            failures.append(f"{tool}:exit_code_missing")
        if not item.get("command"):
            failures.append(f"{tool}:command_missing")
        if not item.get("version"):
            failures.append(f"{tool}:version_missing")
        normalized.append({
            "tool": tool,
            "artifact_path": str(artifact),
            "artifact_sha256": actual_hash,
            "exit_code": item.get("exit_code"),
            "commit_sha": item.get("commit_sha"),
        })

    if failures:
        raise RuntimeError("Scanner release evidence incomplete: " + ", ".join(sorted(failures)))

    return {
        "version": VERSION,
        "complete": True,
        "assessed_revision": assessed_revision,
        "verified_tools": sorted(required_tools),
        "records": normalized,
        "client_delivery_allowed": False,
    }


__all__ = ["verify_scanner_release_evidence"]
