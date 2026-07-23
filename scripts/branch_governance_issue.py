#!/usr/bin/env python3
"""Publish branch-governance evidence and parse owner-approved cleanup commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

INVENTORY_MARKER = "<!-- nico-branch-governance-inventory -->"
CLEANUP_MARKER = "<!-- nico-branch-governance-cleanup -->"
ISSUE_NUMBER = 744
CONFIRMATION_TOKEN = "DELETE_REVIEWED_MERGED_BRANCHES"
CONFIRMATION_PHRASE = "DELETE REVIEWED MERGED BRANCHES"
_EXECUTE_PATTERN = re.compile(
    r"^/branch-cleanup execute batch=(?P<batch>[1-9][0-9]?) "
    r"manifest=(?P<manifest>[0-9a-f]{64}) confirm=" + CONFIRMATION_TOKEN + r"$"
)
_DRY_RUN_PATTERN = re.compile(r"^/branch-cleanup dry-run batch=(?P<batch>[1-9][0-9]?)$")


def manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_cleanup_command(body: str) -> dict[str, Any]:
    normalized = " ".join(str(body or "").strip().split())
    dry = _DRY_RUN_PATTERN.fullmatch(normalized)
    if dry:
        return {
            "mode": "dry-run",
            "batch_size": int(dry.group("batch")),
            "manifest_sha256": "",
            "confirmation": "",
        }
    execute = _EXECUTE_PATTERN.fullmatch(normalized)
    if execute:
        return {
            "mode": "execute",
            "batch_size": int(execute.group("batch")),
            "manifest_sha256": execute.group("manifest"),
            "confirmation": CONFIRMATION_PHRASE,
        }
    raise ValueError(
        "Command must be exactly '/branch-cleanup dry-run batch=N' or "
        "'/branch-cleanup execute batch=N manifest=<64 lowercase hex> "
        f"confirm={CONFIRMATION_TOKEN}', where N is 1-99."
    )


def inventory_comment(inventory_path: Path, manifest_path: Path, run_url: str) -> str:
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    candidates = [
        str(item.get("branch"))
        for item in records
        if isinstance(item, dict) and item.get("deletion_candidate") is True
    ]
    counts = payload.get("classification_counts") if isinstance(payload.get("classification_counts"), dict) else {}
    digest = manifest_sha256(manifest_path)
    lines = [
        INVENTORY_MARKER,
        "## Current branch-governance inventory",
        "",
        f"- Total remote branches: **{int(payload.get('branch_count') or len(records))}**",
        f"- Proven merged deletion candidates: **{len(candidates)}**",
        f"- Manifest SHA-256: `{digest}`",
        f"- Evidence run: {run_url}",
        "",
        "### Classification counts",
        "",
    ]
    for name, count in sorted(counts.items()):
        lines.append(f"- `{name}`: **{int(count)}**")
    lines.extend([
        "",
        "### First reviewed-candidate page",
        "",
        "<details><summary>Show up to 50 candidate branch names</summary>",
        "",
    ])
    lines.extend(f"- `{branch}`" for branch in candidates[:50])
    if not candidates:
        lines.append("- No branches currently satisfy the deletion contract.")
    lines.extend([
        "",
        "</details>",
        "",
        "No branch was deleted by this inventory. Start a fresh validation with:",
        "",
        "`/branch-cleanup dry-run batch=99`",
        "",
        "Execution remains impossible until a dry-run result is reviewed and its exact fresh manifest hash is supplied.",
    ])
    return "\n".join(lines)


def cleanup_comment(result_path: Path, run_url: str, succeeded: bool) -> str:
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        mode = str(result.get("mode") or "unknown")
        digest = str(result.get("manifest_sha256") or "")
        candidates = int(result.get("candidate_count") or 0)
        deleted = [str(item) for item in result.get("deleted", [])]
        lines = [
            CLEANUP_MARKER,
            f"## Branch cleanup {mode} result",
            "",
            f"- Status: **{'successful' if succeeded else 'failed'}**",
            f"- Fresh manifest SHA-256: `{digest}`",
            f"- Candidates validated in this batch: **{candidates}**",
            f"- Branches deleted: **{len(deleted)}**",
            f"- Evidence run: {run_url}",
        ]
        if mode == "dry-run" and succeeded:
            lines.extend([
                "",
                "Review the fresh inventory artifact. To execute this exact unchanged batch, post:",
                "",
                f"`/branch-cleanup execute batch={max(1, min(99, candidates or 99))} manifest={digest} confirm={CONFIRMATION_TOKEN}`",
            ])
        if deleted:
            lines.extend(["", "<details><summary>Deleted branch names</summary>", ""])
            lines.extend(f"- `{branch}`" for branch in deleted)
            lines.extend(["", "</details>"])
        return "\n".join(lines)
    return "\n".join([
        CLEANUP_MARKER,
        "## Branch cleanup failed before a result artifact was produced",
        "",
        f"- Evidence run: {run_url}",
        "- No successful deletion result is claimed. Review the workflow error before retrying.",
    ])


def _api_request(url: str, token: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "nico-branch-governance-issue",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed ({exc.code}) for {url}: {detail}") from exc


def post_comment(repository: str, token: str, body: str, *, upsert_marker: str | None = None) -> None:
    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    comments_url = f"{api_root}/repos/{repository}/issues/{ISSUE_NUMBER}/comments"
    if upsert_marker:
        comments = _api_request(f"{comments_url}?per_page=100", token)
        if isinstance(comments, list):
            for comment in comments:
                if not isinstance(comment, dict) or upsert_marker not in str(comment.get("body") or ""):
                    continue
                comment_id = comment.get("id")
                if isinstance(comment_id, int):
                    _api_request(
                        f"{api_root}/repos/{repository}/issues/comments/{comment_id}",
                        token,
                        method="PATCH",
                        payload={"body": body},
                    )
                    return
    _api_request(comments_url, token, method="POST", payload={"body": body})


def emit_command(body: str, output_path: Path) -> None:
    command = parse_cleanup_command(body)
    output_path.write_text(json.dumps(command, sort_keys=True) + "\n", encoding="utf-8")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            for key in ("mode", "batch_size", "manifest_sha256", "confirmation"):
                handle.write(f"{key}={command[key]}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse-command")
    parse.add_argument("--body", required=True)
    parse.add_argument("--output", type=Path, required=True)

    inventory = sub.add_parser("post-inventory")
    inventory.add_argument("--repository", required=True)
    inventory.add_argument("--inventory", type=Path, required=True)
    inventory.add_argument("--manifest", type=Path, required=True)
    inventory.add_argument("--run-url", required=True)

    cleanup = sub.add_parser("post-cleanup")
    cleanup.add_argument("--repository", required=True)
    cleanup.add_argument("--result", type=Path, required=True)
    cleanup.add_argument("--run-url", required=True)
    cleanup.add_argument("--succeeded", choices=("true", "false"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "parse-command":
        emit_command(args.body, args.output)
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN is required to post governance evidence")
    if args.command == "post-inventory":
        body = inventory_comment(args.inventory, args.manifest, args.run_url)
        post_comment(args.repository, token, body, upsert_marker=INVENTORY_MARKER)
        return 0
    if args.command == "post-cleanup":
        body = cleanup_comment(args.result, args.run_url, args.succeeded == "true")
        post_comment(args.repository, token, body)
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"branch governance issue control failed: {exc}", file=sys.stderr)
        raise
