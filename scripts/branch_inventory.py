#!/usr/bin/env python3
"""Generate a read-only, evidence-backed inventory of every remote branch.

The script never mutates GitHub. It classifies branches using local Git history,
open pull-request heads, GitHub protection metadata, and branch-name safeguards.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


RELEASE_PATTERN = re.compile(
    r"(?:^|/)(?:release|releases|prod|production|deploy|deployment|hotfix|"
    r"recovery|restore|backup|archive)(?:$|/|[-_])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BranchRecord:
    branch: str
    head_sha: str
    last_commit_at: str
    age_days: int
    ahead_of_default: int
    behind_default: int
    protected: bool
    open_pr_numbers: str
    classification: str
    deletion_candidate: bool
    reason: str


def run_git(repo_dir: Path, *args: str) -> str:
    command = ["git", "-C", str(repo_dir), *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Git command failed ({' '.join(command)}): {message}")
    return completed.stdout.strip()


def api_get(url: str, token: str) -> tuple[Any, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nico-branch-governance-inventory",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed ({exc.code}) for {url}: {detail}") from exc


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for segment in link_header.split(","):
        pieces = [piece.strip() for piece in segment.split(";")]
        if len(pieces) < 2 or pieces[1] != 'rel="next"':
            continue
        return pieces[0].strip("<>")
    return None


def paginated_api(path: str, repository: str, token: str) -> list[dict[str, Any]]:
    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api_root}/repos/{repository}/{path}"
    rows: list[dict[str, Any]] = []
    while url:
        payload, headers = api_get(url, token)
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected a list from GitHub API path {path}")
        rows.extend(item for item in payload if isinstance(item, dict))
        url = parse_next_link(headers.get("Link") or headers.get("link"))
    return rows


def remote_branches(repo_dir: Path, remote: str) -> list[str]:
    refs = run_git(
        repo_dir,
        "for-each-ref",
        "--format=%(refname:strip=3)",
        f"refs/remotes/{remote}",
    ).splitlines()
    return sorted({ref for ref in refs if ref and ref != "HEAD"})


def parse_commit_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def open_pull_requests(repository: str, token: str) -> dict[str, list[int]]:
    encoded = urllib.parse.urlencode({"state": "open", "per_page": 100})
    pulls = paginated_api(f"pulls?{encoded}", repository, token)
    by_branch: dict[str, list[int]] = {}
    for pull in pulls:
        head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
        branch = str(head.get("ref") or "")
        number = pull.get("number")
        if branch and isinstance(number, int):
            by_branch.setdefault(branch, []).append(number)
    return by_branch


def protected_branches(repository: str, token: str) -> set[str]:
    encoded = urllib.parse.urlencode({"per_page": 100})
    branches = paginated_api(f"branches?{encoded}", repository, token)
    return {
        str(branch.get("name"))
        for branch in branches
        if branch.get("protected") is True and branch.get("name")
    }


def classify(
    *,
    branch: str,
    default_branch: str,
    protected: bool,
    open_prs: Iterable[int],
    ahead: int,
    age_days: int,
    stale_days: int,
) -> tuple[str, bool, str]:
    pull_numbers = list(open_prs)
    if branch == default_branch:
        return "ACTIVE_DEFAULT", False, "Repository default branch"
    if pull_numbers:
        return "OPEN_PR", False, f"Open pull request(s): {', '.join(map(str, pull_numbers))}"
    if protected:
        return "PROTECTED_OR_RELEASE", False, "GitHub reports the branch as protected"
    if RELEASE_PATTERN.search(branch):
        return "DEPLOYMENT_OR_RELEASE", False, "Branch name indicates release, deployment, or recovery use"
    if ahead == 0:
        return "MERGED_SAFE_TO_DELETE", True, "No commits exist on this branch that are absent from the default branch"
    if age_days >= stale_days:
        return (
            "STALE_WITH_UNMERGED_COMMITS",
            False,
            f"Contains {ahead} unique commit(s) and has not advanced for {age_days} days",
        )
    return (
        "MANUAL_REVIEW",
        False,
        f"Contains {ahead} unique commit(s) and has recent activity",
    )


def inventory(
    *,
    repo_dir: Path,
    repository: str,
    default_branch: str,
    remote: str,
    token: str,
    stale_days: int,
) -> list[BranchRecord]:
    default_ref = f"refs/remotes/{remote}/{default_branch}"
    run_git(repo_dir, "rev-parse", "--verify", default_ref)

    pulls_by_branch = open_pull_requests(repository, token)
    protected = protected_branches(repository, token)
    now = datetime.now(timezone.utc)
    records: list[BranchRecord] = []

    for branch in remote_branches(repo_dir, remote):
        branch_ref = f"refs/remotes/{remote}/{branch}"
        head_sha = run_git(repo_dir, "rev-parse", branch_ref)
        committed_at = run_git(repo_dir, "show", "-s", "--format=%cI", branch_ref)
        commit_time = parse_commit_time(committed_at)
        age_days = max(0, (now - commit_time).days)
        ahead = int(run_git(repo_dir, "rev-list", "--count", f"{default_ref}..{branch_ref}"))
        behind = int(run_git(repo_dir, "rev-list", "--count", f"{branch_ref}..{default_ref}"))
        open_prs = sorted(pulls_by_branch.get(branch, []))
        classification, deletion_candidate, reason = classify(
            branch=branch,
            default_branch=default_branch,
            protected=branch in protected,
            open_prs=open_prs,
            ahead=ahead,
            age_days=age_days,
            stale_days=stale_days,
        )
        records.append(
            BranchRecord(
                branch=branch,
                head_sha=head_sha,
                last_commit_at=commit_time.isoformat().replace("+00:00", "Z"),
                age_days=age_days,
                ahead_of_default=ahead,
                behind_default=behind,
                protected=branch in protected,
                open_pr_numbers=",".join(map(str, open_prs)),
                classification=classification,
                deletion_candidate=deletion_candidate,
                reason=reason,
            )
        )
    return records


def write_outputs(
    *,
    output_dir: Path,
    repository: str,
    default_branch: str,
    stale_days: int,
    records: list[BranchRecord],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    counts = Counter(record.classification for record in records)
    candidates = [record for record in records if record.deletion_candidate]

    json_payload = {
        "schema_version": "nico.branch_inventory.v1",
        "generated_at": generated_at,
        "repository": repository,
        "default_branch": default_branch,
        "stale_days": stale_days,
        "branch_count": len(records),
        "classification_counts": dict(sorted(counts.items())),
        "records": [asdict(record) for record in records],
    }
    (output_dir / "branch-inventory.json").write_text(
        json.dumps(json_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    fields = list(BranchRecord.__dataclass_fields__)
    with (output_dir / "branch-inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)

    (output_dir / "safe-delete-branches.txt").write_text(
        "".join(f"{record.branch}\n" for record in candidates),
        encoding="utf-8",
    )

    summary_lines = [
        "# NICO branch-governance inventory",
        "",
        f"- Generated: `{generated_at}`",
        f"- Repository: `{repository}`",
        f"- Default branch: `{default_branch}`",
        f"- Total remote branches: **{len(records)}**",
        f"- Proven merged deletion candidates: **{len(candidates)}**",
        f"- Stale threshold: **{stale_days} days**",
        "",
        "## Classification counts",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    summary_lines.extend(f"| `{name}` | {count} |" for name, count in sorted(counts.items()))
    summary_lines.extend(
        [
            "",
            "## Safety statement",
            "",
            "This workflow is read-only. `safe-delete-branches.txt` contains only branches with no open pull request, no GitHub protection, no release/deployment naming safeguard, and zero commits absent from the default branch. Human approval is still required before deletion.",
            "",
        ]
    )
    (output_dir / "branch-summary.md").write_text("\n".join(summary_lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, help="Repository in owner/name form")
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--output-dir", type=Path, default=Path("branch-governance"))
    parser.add_argument("--stale-days", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stale_days < 1:
        raise ValueError("--stale-days must be at least 1")
    token = os.environ.get("GITHUB_TOKEN", "")
    records = inventory(
        repo_dir=args.repo_dir.resolve(),
        repository=args.repository,
        default_branch=args.default_branch,
        remote=args.remote,
        token=token,
        stale_days=args.stale_days,
    )
    write_outputs(
        output_dir=args.output_dir,
        repository=args.repository,
        default_branch=args.default_branch,
        stale_days=args.stale_days,
        records=records,
    )
    print(f"Inventoried {len(records)} branches; no repository mutations were performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - workflow-level diagnostic
        print(f"branch inventory failed: {exc}", file=sys.stderr)
        raise
