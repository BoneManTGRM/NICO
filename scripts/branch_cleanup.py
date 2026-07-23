#!/usr/bin/env python3
"""Delete only human-approved branches proven merged by a fresh inventory.

The executor defaults to dry-run. Execution requires an exact confirmation phrase
and the SHA-256 of the freshly generated safe-delete manifest. Every branch is
revalidated through GitHub immediately before deletion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIRMATION_PHRASE = "DELETE REVIEWED MERGED BRANCHES"
MAX_BATCH_SIZE = 100


@dataclass(frozen=True)
class Candidate:
    branch: str
    head_sha: str


def manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_candidates(inventory_path: Path, manifest_path: Path) -> list[Candidate]:
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Inventory records are missing")

    safe_by_name: dict[str, Candidate] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("classification") != "MERGED_SAFE_TO_DELETE":
            continue
        if record.get("deletion_candidate") is not True:
            continue
        branch = str(record.get("branch") or "").strip()
        head_sha = str(record.get("head_sha") or "").strip()
        if not branch or len(head_sha) != 40:
            raise ValueError(f"Invalid deletion candidate record: {record!r}")
        safe_by_name[branch] = Candidate(branch=branch, head_sha=head_sha)

    manifest_names = [
        line.strip()
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(manifest_names) != len(set(manifest_names)):
        raise ValueError("Safe-delete manifest contains duplicate branch names")

    unknown = [name for name in manifest_names if name not in safe_by_name]
    if unknown:
        raise ValueError(f"Manifest contains branches not proven safe: {unknown[:5]}")
    return [safe_by_name[name] for name in manifest_names]


def api_request(url: str, token: str, *, method: str = "GET") -> Any:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "nico-branch-governance-cleanup",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            if not body:
                return None
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed ({exc.code}) for {url}: {detail}") from exc


def validate_live_candidate(repository: str, token: str, candidate: Candidate) -> None:
    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    encoded_branch = urllib.parse.quote(candidate.branch, safe="")
    branch_url = f"{api_root}/repos/{repository}/branches/{encoded_branch}"
    branch_payload = api_request(branch_url, token)
    if not isinstance(branch_payload, dict):
        raise RuntimeError(f"Unable to verify branch {candidate.branch}")
    if branch_payload.get("protected") is True:
        raise RuntimeError(f"Branch became protected: {candidate.branch}")
    commit = branch_payload.get("commit") if isinstance(branch_payload.get("commit"), dict) else {}
    live_sha = str(commit.get("sha") or "")
    if live_sha != candidate.head_sha:
        raise RuntimeError(
            f"Branch changed after inventory: {candidate.branch} expected={candidate.head_sha} live={live_sha}"
        )

    owner = repository.split("/", 1)[0]
    query = urllib.parse.urlencode(
        {"state": "open", "head": f"{owner}:{candidate.branch}", "per_page": 1}
    )
    pulls_url = f"{api_root}/repos/{repository}/pulls?{query}"
    pulls = api_request(pulls_url, token)
    if isinstance(pulls, list) and pulls:
        raise RuntimeError(f"Branch now has an open pull request: {candidate.branch}")


def delete_branch(repository: str, token: str, branch: str) -> None:
    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    encoded_ref = urllib.parse.quote(f"heads/{branch}", safe="/")
    api_request(f"{api_root}/repos/{repository}/git/refs/{encoded_ref}", token, method="DELETE")


def execute(
    *,
    repository: str,
    token: str,
    inventory_path: Path,
    manifest_path: Path,
    expected_manifest_sha256: str,
    mode: str,
    confirmation: str,
    batch_size: int,
    output_path: Path,
) -> dict[str, Any]:
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")

    actual_hash = manifest_sha256(manifest_path)
    if expected_manifest_sha256 and actual_hash != expected_manifest_sha256.lower():
        raise ValueError(
            f"Manifest hash mismatch: expected={expected_manifest_sha256.lower()} actual={actual_hash}"
        )

    candidates = load_candidates(inventory_path, manifest_path)[:batch_size]
    result: dict[str, Any] = {
        "schema_version": "nico.branch_cleanup.v1",
        "repository": repository,
        "mode": mode,
        "manifest_sha256": actual_hash,
        "batch_size": batch_size,
        "candidate_count": len(candidates),
        "deleted": [],
        "validated": [],
    }

    if mode == "execute":
        if confirmation != CONFIRMATION_PHRASE:
            raise ValueError("Execution confirmation phrase is incorrect")
        if not expected_manifest_sha256:
            raise ValueError("Execution requires expected_manifest_sha256 from a reviewed dry run")
        if not token:
            raise ValueError("GITHUB_TOKEN is required for execution")

    for candidate in candidates:
        if mode == "execute":
            validate_live_candidate(repository, token, candidate)
        result["validated"].append({"branch": candidate.branch, "head_sha": candidate.head_sha})
        if mode == "execute":
            delete_branch(repository, token, candidate.branch)
            result["deleted"].append(candidate.branch)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", default="")
    parser.add_argument("--mode", choices=("dry-run", "execute"), default="dry-run")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("branch-governance/cleanup-result.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = execute(
        repository=args.repository,
        token=os.environ.get("GITHUB_TOKEN", ""),
        inventory_path=args.inventory,
        manifest_path=args.manifest,
        expected_manifest_sha256=args.expected_manifest_sha256.strip().lower(),
        mode=args.mode,
        confirmation=args.confirmation,
        batch_size=args.batch_size,
        output_path=args.output,
    )
    print(json.dumps({
        "mode": result["mode"],
        "candidate_count": result["candidate_count"],
        "deleted_count": len(result["deleted"]),
        "manifest_sha256": result["manifest_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"branch cleanup failed: {exc}", file=sys.stderr)
        raise
