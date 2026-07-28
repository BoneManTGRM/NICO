#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
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

_RETRYABLE_HTTP_STATUS = {403, 408, 409, 429, 500, 502, 503, 504}


def _retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = str(error.headers.get("Retry-After") or "").strip()
    if retry_after.isdigit():
        return min(120.0, max(1.0, float(retry_after)))
    reset = str(error.headers.get("X-RateLimit-Reset") or "").strip()
    if reset.isdigit():
        return min(120.0, max(1.0, float(reset) - time.time() + 1.0))
    return min(60.0, float(2 ** min(attempt, 5)))


def _request(url: str, token: str, *, attempts: int = 10) -> dict[str, Any]:
    last_error: BaseException | None = None
    for attempt in range(max(1, attempts)):
        request = urllib.request.Request(url)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("User-Agent", "NICO-phase6-ci-truth")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310 - fixed GitHub API host
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("GitHub API response was not an object")
            return payload
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in _RETRYABLE_HTTP_STATUS or attempt + 1 >= attempts:
                raise
            delay = _retry_delay(error, attempt)
            print(
                f"GitHub API request retry {attempt + 1}/{attempts - 1}: "
                f"status={error.code} delay_seconds={delay:.0f} url={url}",
                flush=True,
            )
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt + 1 >= attempts:
                raise
            delay = min(60.0, float(2 ** min(attempt, 5)))
            print(
                f"GitHub API transport retry {attempt + 1}/{attempts - 1}: "
                f"delay_seconds={delay:.0f} error={error}",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"GitHub API request failed after retries: {last_error}")


def _api(repository: str, path: str, token: str, **query: Any) -> dict[str, Any]:
    encoded = urllib.parse.urlencode({key: value for key, value in query.items() if value is not None})
    suffix = f"?{encoded}" if encoded else ""
    base = f"https://api.github.com/repos/{repository}"
    resource = f"/{path.lstrip('/')}" if path else ""
    return _request(f"{base}{resource}{suffix}", token)


def _run_matches_sha(run: dict[str, Any], sha: str) -> bool:
    target = sha.casefold()
    if str(run.get("head_sha") or "").casefold() == target:
        return True
    for pull in run.get("pull_requests") or []:
        if not isinstance(pull, dict):
            continue
        head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
        if str(head.get("sha") or "").casefold() == target:
            return True
    return False


def _runs_for_sha(repository: str, sha: str, token: str) -> list[dict[str, Any]]:
    """Return workflow runs associated with an immutable application SHA.

    GitHub pull-request runs can expose a synthetic merge SHA as ``head_sha`` even
    though their pull-request metadata points at the immutable PR head. Querying
    only ``actions/runs?head_sha=<sha>`` therefore misses valid exact-source runs.
    We combine the direct query with a bounded recent-run scan and accept a run
    only when either its real head SHA or its PR-head metadata matches exactly.
    """
    by_id: dict[int, dict[str, Any]] = {}

    for page in range(1, 4):
        payload = _api(repository, "actions/runs", token, head_sha=sha, per_page=100, page=page)
        page_runs = [dict(item) for item in payload.get("workflow_runs") or [] if isinstance(item, dict)]
        for run in page_runs:
            if _run_matches_sha(run, sha):
                by_id[int(run.get("id") or 0)] = run
        if len(page_runs) < 100:
            break

    for page in range(1, 6):
        payload = _api(repository, "actions/runs", token, per_page=100, page=page)
        page_runs = [dict(item) for item in payload.get("workflow_runs") or [] if isinstance(item, dict)]
        for run in page_runs:
            if _run_matches_sha(run, sha):
                by_id[int(run.get("id") or 0)] = run
        if len(page_runs) < 100:
            break

    return [run for run_id, run in by_id.items() if run_id]


def _run_authority(item: dict[str, Any]) -> tuple[int, str, int, int]:
    status = str(item.get("status") or "unknown").casefold()
    conclusion = str(item.get("conclusion") or "").casefold()
    if status == "completed" and conclusion == "success":
        state_rank = 3
    elif status != "completed":
        state_rank = 2
    else:
        state_rank = 1
    return (
        state_rank,
        str(item.get("updated_at") or ""),
        int(item.get("run_attempt") or 0),
        int(item.get("id") or 0),
    )


def _latest_by_name(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        name = str(run.get("name") or "").strip()
        if name:
            grouped.setdefault(name, []).append(run)
    return {name: max(items, key=_run_authority) for name, items in grouped.items()}


def _project(name: str, run: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run, dict):
        return {"name": name, "status": "not_observed", "conclusion": None, "run_id": None, "url": None}
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
        "authority_rule": "successful exact-source completion, then active exact-source run, then failed exact-source run; newest record breaks ties",
    }


def _duplicate_run_summary(runs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = {}
    for run in runs:
        name = str(run.get("name") or "").strip()
        if not name:
            continue
        status = str(run.get("status") or "unknown").casefold()
        conclusion = str(run.get("conclusion") or "").casefold()
        bucket = "success" if status == "completed" and conclusion == "success" else "active" if status != "completed" else "failed"
        grouped.setdefault(name, {"success": 0, "active": 0, "failed": 0})[bucket] += 1
    return grouped


def _snapshot(repository: str, sha: str, token: str) -> dict[str, Any]:
    runs = _runs_for_sha(repository, sha, token)
    latest = _latest_by_name(runs)
    checks = {name: _project(name, latest.get(name)) for name in REQUIRED_WORKFLOWS}
    observed = [item for item in checks.values() if item["status"] != "not_observed"]
    pending = [name for name, item in checks.items() if item["status"] not in {"completed", "not_observed"}]
    failed = [name for name, item in checks.items() if item["status"] == "completed" and item["conclusion"] != "success"]
    missing = [name for name, item in checks.items() if item["status"] == "not_observed"]
    green = not pending and not failed and not missing
    return {
        "schema": "nico.phase6.required_checks.v4",
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
        "duplicate_exact_source_run_summary": _duplicate_run_summary(runs),
        "pull_request_merge_sha_does_not_hide_exact_pr_head_runs": True,
        "successful_exact_source_run_is_authoritative_over_duplicate_failed_or_active_runs": True,
        "active_or_queued_runs_are_not_failures": True,
    }


def _write_snapshot(path: Path, repository: str, assessed: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "nico.phase6.ci_truth_pending.v4", "repository": repository, "assessed_commit": assessed}, indent=2, sort_keys=True), encoding="utf-8")


def _wait_for_assessed_commit(repository: str, target_sha: str, token: str, *, output_path: Path, wait_seconds: int, poll_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, wait_seconds)
    while True:
        assessed = _snapshot(repository, target_sha, token)
        _write_snapshot(output_path, repository, assessed)
        if assessed["all_required_checks_green"]:
            return assessed
        if time.monotonic() >= deadline:
            raise SystemExit(
                "Timed out waiting for authoritative assessed-commit workflow results: "
                f"failed={assessed['failed']} pending={assessed['pending']} missing={assessed['missing']}"
            )
        print(
            "waiting for authoritative assessed-commit workflows: "
            f"failed={assessed['failed']} pending={assessed['pending']} missing={assessed['missing']}",
            flush=True,
        )
        time.sleep(max(5, poll_seconds))


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
    assessed = _wait_for_assessed_commit(repository, target_sha, token, output_path=args.output, wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds)

    repository_payload = _api(repository, "", token)
    default_branch = str(repository_payload.get("default_branch") or "main")
    branch_payload = _api(repository, f"branches/{urllib.parse.quote(default_branch, safe='')}", token)
    default_sha = str(((branch_payload.get("commit") or {}).get("sha")) or "").lower()
    default_health = _snapshot(repository, default_sha, token) if default_sha else {
        "schema": "nico.phase6.required_checks.v4",
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
        "schema": "nico.phase6.ci_truth_capture.v4",
        "repository": repository,
        "assessed_commit": assessed,
        "current_default_branch": {**default_health, "branch": default_branch},
        "required_workflows": list(REQUIRED_WORKFLOWS),
        "historical_reliability_source": "separate bounded workflow-runs capture",
        "historical_failures_do_not_override_assessed_commit": True,
        "duplicate_failed_or_active_exact_source_runs_do_not_override_a_successful_required_check": True,
        "pull_request_merge_sha_does_not_hide_exact_pr_head_runs": True,
        "active_or_queued_runs_are_not_historical_failures": True,
        "api_transport_retries_enabled": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
