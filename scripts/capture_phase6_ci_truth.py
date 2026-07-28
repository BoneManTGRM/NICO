#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REQUIRED_WORKFLOWS = (
    "NICO CI",
    "Node.js CI",
    "Frontend Production Release Proof",
    "Unified Production Acceptance",
    "Recorded Golden Demonstration",
    "Postgres Restart Proof",
    "Resilience Proof",
    "iOS WebKit Paint Proof",
    "Audit Evidence",
    "Mobile Restart Production Proof",
    "CodeQL Advanced",
    "Security Audit Evidence",
    "Remediation Evidence",
)


def _request(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "NICO-phase6-ci-truth")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310 - fixed GitHub API host
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API response was not an object")
    return payload


def _api(repository: str, path: str, token: str, **query: Any) -> dict[str, Any]:
    encoded = urllib.parse.urlencode({key: value for key, value in query.items() if value is not None})
    suffix = f"?{encoded}" if encoded else ""
    return _request(f"https://api.github.com/repos/{repository}/{path}{suffix}", token)


def _runs_for_sha(repository: str, sha: str, token: str) -> list[dict[str, Any]]:
    payload = _api(repository, "actions/runs", token, head_sha=sha, per_page=100)
    return [dict(item) for item in payload.get("workflow_runs") or [] if isinstance(item, dict)]


def _latest_by_name(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for run in sorted(
        runs,
        key=lambda item: (str(item.get("updated_at") or ""), int(item.get("run_attempt") or 0), int(item.get("id") or 0)),
        reverse=True,
    ):
        name = str(run.get("name") or "").strip()
        if name and name not in output:
            output[name] = run
    return output


def _project(name: str, run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {
            "name": name,
            "status": "not_observed",
            "conclusion": None,
            "run_id": None,
            "url": None,
        }
    return {
        "name": name,
        "status": str(run.get("status") or "unknown"),
        "conclusion": run.get("conclusion"),
        "run_id": run.get("id"),
        "run_number": run.get("run_number"),
        "run_attempt": run.get("run_attempt"),
        "event": run.get("event"),
        "head_sha": run.get("head_sha"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "url": run.get("html_url"),
    }


def _snapshot(repository: str, sha: str, token: str) -> dict[str, Any]:
    latest = _latest_by_name(_runs_for_sha(repository, sha, token))
    checks = {name: _project(name, latest.get(name)) for name in REQUIRED_WORKFLOWS}
    observed = [item for item in checks.values() if item["status"] != "not_observed"]
    pending = [name for name, item in checks.items() if item["status"] not in {"completed", "not_observed"}]
    failed = [name for name, item in checks.items() if item["status"] == "completed" and item["conclusion"] != "success"]
    missing = [name for name, item in checks.items() if item["status"] == "not_observed"]
    green = not pending and not failed and not missing
    return {
        "schema": "nico.phase6.required_checks.v1",
        "commit_sha": sha,
        "all_required_checks_green": green,
        "required_checks_green": green,
        "status": "green" if green else "pending" if pending else "not_green" if failed else "not_observed",
        "checks": checks,
        "observed_count": len(observed),
        "required_count": len(REQUIRED_WORKFLOWS),
        "pending": pending,
        "failed": failed,
        "missing": missing,
        "active_or_queued_runs_are_not_failures": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture exact-commit, default-branch, and historical CI truth for Phase 6.")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=2700)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()

    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""
    if not token:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required")
    repository = args.repository.strip()
    target_sha = args.target_sha.strip().lower()
    deadline = time.monotonic() + max(0, args.wait_seconds)

    while True:
        assessed = _snapshot(repository, target_sha, token)
        if assessed["all_required_checks_green"]:
            break
        if assessed["failed"]:
            raise SystemExit(f"Required assessed-commit workflows failed: {assessed['failed']}")
        if time.monotonic() >= deadline:
            raise SystemExit(
                "Timed out waiting for assessed-commit workflows: "
                f"pending={assessed['pending']} missing={assessed['missing']}"
            )
        print(
            "waiting for assessed-commit workflows: "
            f"pending={assessed['pending']} missing={assessed['missing']}",
            flush=True,
        )
        time.sleep(max(5, args.poll_seconds))

    repository_payload = _api(repository, "", token)
    default_branch = str(repository_payload.get("default_branch") or "main")
    branch_payload = _api(repository, f"branches/{urllib.parse.quote(default_branch, safe='')}", token)
    default_sha = str(((branch_payload.get("commit") or {}).get("sha")) or "").lower()
    default_health = _snapshot(repository, default_sha, token) if default_sha else {
        "schema": "nico.phase6.required_checks.v1",
        "commit_sha": "",
        "status": "not_observed",
        "all_required_checks_green": None,
        "required_checks_green": None,
        "checks": {},
        "observed_count": 0,
        "required_count": len(REQUIRED_WORKFLOWS),
        "pending": [],
        "failed": [],
        "missing": list(REQUIRED_WORKFLOWS),
    }
    output = {
        "schema": "nico.phase6.ci_truth_capture.v1",
        "repository": repository,
        "assessed_commit": assessed,
        "current_default_branch": {
            **default_health,
            "branch": default_branch,
        },
        "required_workflows": list(REQUIRED_WORKFLOWS),
        "historical_reliability_source": "separate bounded workflow-runs capture",
        "historical_failures_do_not_override_assessed_commit": True,
        "active_or_queued_runs_are_not_historical_failures": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
