from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from nico.hosted_assessment import GitHubAssessmentClient, normalize_repository, parse_dt

RETAINER_EVIDENCE_SCHEMA = "nico.retainer_evidence_ingestion.v1"
DEFAULT_TIMEFRAME_DAYS = 30
MAX_TIMEFRAME_DAYS = 365
MAX_SOURCE_ITEMS = 100
MAX_PUBLIC_ITEMS = 30
BLOCKER_LABELS = {
    "blocker",
    "blocked",
    "critical",
    "high",
    "high-priority",
    "priority-high",
    "security",
    "sev-1",
    "sev-2",
    "p0",
    "p1",
}
FAILED_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "startup_failure",
    "stale",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_days(value: Any) -> int:
    try:
        days = int(value or DEFAULT_TIMEFRAME_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_TIMEFRAME_DAYS
    return max(1, min(days, MAX_TIMEFRAME_DAYS))


def _safe_provider_note(error: str | None) -> str:
    if not error:
        return ""
    status = re.search(r"returned\s+(\d{3})", str(error), flags=re.IGNORECASE)
    if status:
        return f"GitHub source returned HTTP {status.group(1)}."
    if "non-json" in str(error).lower():
        return "GitHub source returned an unreadable response."
    return "GitHub source was unavailable during this evidence refresh."


def _source(
    source_id: str,
    *,
    status: str,
    checked_at: str,
    item_count: int | None,
    note: str = "",
    derived_from: str = "",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "status": status,
        "checked_at": checked_at,
        "item_count": item_count,
        "note": str(note or "")[:240],
        "derived_from": str(derived_from or "")[:80],
    }


def _labels(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for label in item.get("labels") or []:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip().lower()
        else:
            name = str(label or "").strip().lower()
        if name:
            values.append(name)
    return values


def _commit_line(item: dict[str, Any]) -> str:
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    message = str(commit.get("message") or "").splitlines()[0].strip()
    sha = str(item.get("sha") or "")[:12]
    created = str(author.get("date") or "")
    login = ""
    if isinstance(item.get("author"), dict):
        login = str(item["author"].get("login") or "")
    attribution = login or str(author.get("name") or "unknown")
    return f"{sha} · {message or 'Commit message unavailable'} · {attribution} · {created or 'time unavailable'}"


def _pull_line(item: dict[str, Any]) -> str:
    number = item.get("number")
    title = str(item.get("title") or "Untitled pull request").strip()
    merged = bool(item.get("merged_at"))
    state = "merged" if merged else str(item.get("state") or "unknown")
    changed = str(item.get("updated_at") or item.get("created_at") or "")
    return f"PR #{number} · {state} · {title} · {changed or 'time unavailable'}"


def _issue_line(item: dict[str, Any]) -> str:
    number = item.get("number")
    title = str(item.get("title") or "Untitled issue").strip()
    state = str(item.get("state") or "unknown")
    labels = ", ".join(_labels(item)) or "no labels"
    changed = str(item.get("updated_at") or item.get("created_at") or "")
    return f"Issue #{number} · {state} · {title} · labels={labels} · {changed or 'time unavailable'}"


def _workflow_line(item: dict[str, Any]) -> str:
    name = str(item.get("name") or item.get("display_title") or "Unnamed workflow")
    conclusion = str(item.get("conclusion") or item.get("status") or "unknown")
    event = str(item.get("event") or "unknown")
    created = str(item.get("created_at") or "")
    head_sha = str(item.get("head_sha") or "")[:12]
    return f"{name} · {conclusion} · event={event} · sha={head_sha or 'unavailable'} · {created or 'time unavailable'}"


def _release_line(item: dict[str, Any]) -> str:
    tag = str(item.get("tag_name") or "untagged")
    name = str(item.get("name") or tag)
    state = "draft" if item.get("draft") else "prerelease" if item.get("prerelease") else "published"
    published = str(item.get("published_at") or item.get("created_at") or "")
    return f"{tag} · {state} · {name} · {published or 'time unavailable'}"


def _deployment_line(item: dict[str, Any]) -> str:
    deployment_id = str(item.get("id") or "unknown")
    environment = str(item.get("environment") or "default")
    ref = str(item.get("ref") or "unknown")
    sha = str(item.get("sha") or "")[:12]
    created = str(item.get("created_at") or "")
    return f"Deployment {deployment_id} · environment={environment} · ref={ref} · sha={sha or 'unavailable'} · {created or 'time unavailable'}"


def _within_window(item: dict[str, Any], since: datetime, *keys: str) -> bool:
    for key in keys:
        parsed = parse_dt(str(item.get(key) or ""))
        if parsed is not None:
            return parsed >= since
    return True


def _matching_baseline(
    candidate: dict[str, Any] | None,
    *,
    repository: str,
    customer_id: str,
    project_id: str,
    baseline_type: str,
) -> dict[str, Any] | None:
    if not isinstance(candidate, dict) or not candidate:
        return None
    candidate_repository = str(candidate.get("repository") or "").strip()
    try:
        normalized_candidate = normalize_repository(candidate_repository)
    except ValueError:
        return None
    if normalized_candidate != repository:
        return None
    candidate_customer = str(candidate.get("customer_id") or customer_id)
    candidate_project = str(candidate.get("project_id") or project_id)
    if candidate_customer != customer_id or candidate_project != project_id:
        return None
    snapshot = candidate.get("repository_snapshot") if isinstance(candidate.get("repository_snapshot"), dict) else {}
    scanner = candidate.get("scanner") if isinstance(candidate.get("scanner"), dict) else {}
    return {
        "status": "matched",
        "baseline_type": baseline_type,
        "run_id": str(candidate.get("run_id") or ""),
        "repository": repository,
        "customer_id": customer_id,
        "project_id": project_id,
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "snapshot_commit_sha": str(snapshot.get("commit_sha") or ""),
        "scanner_id": str(scanner.get("scan_id") or ""),
        "generated_at": candidate.get("generated_at"),
    }


def _record_response(record: dict[str, Any]) -> dict[str, Any] | None:
    response = record.get("response")
    if isinstance(response, dict) and response:
        return deepcopy(response)
    payload = record.get("payload")
    if isinstance(payload, dict) and payload.get("run_id"):
        return deepcopy(payload)
    return None


def resolve_retainer_baseline(
    payload: dict[str, Any],
    *,
    latest_express: dict[str, Any] | None = None,
    latest_mid: dict[str, Any] | None = None,
    store: Any = None,
) -> dict[str, Any]:
    repository_value = str(payload.get("repository") or "").strip()
    explicit_run_id = str(payload.get("baseline_run_id") or "").strip()
    customer_id = str(payload.get("customer_id") or "default_customer")
    project_id = str(payload.get("project_id") or "default_project")

    explicit_record: dict[str, Any] | None = None
    if explicit_run_id and store is not None:
        try:
            stored = store.get("assessment_runs", explicit_run_id)
        except Exception:
            stored = None
        if isinstance(stored, dict):
            explicit_record = _record_response(stored)
            if explicit_record is not None:
                explicit_record.setdefault("customer_id", stored.get("customer_id") or customer_id)
                explicit_record.setdefault("project_id", stored.get("project_id") or project_id)
                explicit_record.setdefault("repository", stored.get("repository") or repository_value)

    candidates = [
        (explicit_record, "explicit_run"),
        (latest_mid, "mid"),
        (latest_express, "express"),
    ]

    if not repository_value:
        for candidate, _baseline_type in candidates:
            if isinstance(candidate, dict) and candidate.get("repository"):
                repository_value = str(candidate.get("repository") or "")
                break
    if not repository_value:
        return {
            "status": "not_available",
            "baseline_type": "none",
            "run_id": "",
            "repository": "",
            "customer_id": customer_id,
            "project_id": project_id,
            "snapshot_id": "",
            "snapshot_commit_sha": "",
            "scanner_id": "",
        }
    try:
        repository = normalize_repository(repository_value)
    except ValueError:
        return {
            "status": "invalid_repository",
            "baseline_type": "none",
            "run_id": "",
            "repository": repository_value[:200],
            "customer_id": customer_id,
            "project_id": project_id,
            "snapshot_id": "",
            "snapshot_commit_sha": "",
            "scanner_id": "",
        }

    for candidate, baseline_type in candidates:
        matched = _matching_baseline(
            candidate,
            repository=repository,
            customer_id=customer_id,
            project_id=project_id,
            baseline_type=baseline_type,
        )
        if matched is not None:
            if explicit_run_id and matched.get("run_id") != explicit_run_id and baseline_type == "explicit_run":
                continue
            return matched

    if store is not None:
        try:
            records = store.list("assessment_runs", customer_id=customer_id, project_id=project_id)
        except Exception:
            records = []
        ordered = sorted(
            [item for item in records if isinstance(item, dict)],
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        for record in ordered[:100]:
            candidate = _record_response(record)
            if candidate is None:
                continue
            candidate.setdefault("customer_id", record.get("customer_id") or customer_id)
            candidate.setdefault("project_id", record.get("project_id") or project_id)
            candidate.setdefault("repository", record.get("repository") or repository)
            matched = _matching_baseline(
                candidate,
                repository=repository,
                customer_id=customer_id,
                project_id=project_id,
                baseline_type=str(record.get("workflow") or "stored_run"),
            )
            if matched is not None:
                if explicit_run_id and matched.get("run_id") != explicit_run_id:
                    continue
                return matched

    return {
        "status": "repository_only",
        "baseline_type": "none",
        "run_id": "",
        "repository": repository,
        "customer_id": customer_id,
        "project_id": project_id,
        "snapshot_id": "",
        "snapshot_commit_sha": "",
        "scanner_id": "",
    }


def _generic_list(
    client: GitHubAssessmentClient,
    repository: str,
    path: str,
    params: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str | None]:
    data, error = client.get_json(client.repo_url(repository, path), params)
    if error:
        return [], error
    if not isinstance(data, list):
        return [], "GitHub source did not return a list."
    return [item for item in data if isinstance(item, dict)], None


def build_retainer_evidence_payload(
    payload: dict[str, Any],
    *,
    latest_express: dict[str, Any] | None = None,
    latest_mid: dict[str, Any] | None = None,
    store: Any = None,
    client: GitHubAssessmentClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    enriched = deepcopy(payload)
    checked = now or _now()
    checked_at = _iso(checked)
    timeframe_days = _bounded_days(payload.get("timeframe_days"))
    since = checked - timedelta(days=timeframe_days)
    since_iso = _iso(since)
    baseline = resolve_retainer_baseline(
        payload,
        latest_express=latest_express,
        latest_mid=latest_mid,
        store=store,
    )
    repository = str(baseline.get("repository") or "")

    if baseline.get("status") == "invalid_repository":
        enriched["repository"] = repository
        enriched["source_binding"] = {
            "status": "invalid",
            "repository": repository,
            "checked_at": checked_at,
            "timeframe_days": timeframe_days,
            "baseline": baseline,
            "observed_commit_sha": "",
        }
        enriched["retainer_evidence_sources"] = {}
        enriched["blocker_verification"] = {
            "status": "unverified",
            "checked_sources": [],
            "blocker_count": None,
            "reason": "repository_identity_invalid",
        }
        enriched["technical_evidence_auto_ingested"] = False
        return enriched

    if not repository:
        enriched["source_binding"] = {
            "status": "unbound",
            "repository": "",
            "checked_at": checked_at,
            "timeframe_days": timeframe_days,
            "baseline": baseline,
            "observed_commit_sha": "",
        }
        enriched["retainer_evidence_sources"] = {}
        enriched["blocker_verification"] = {
            "status": "unverified",
            "checked_sources": [],
            "blocker_count": None,
            "reason": "repository_not_bound",
        }
        enriched["technical_evidence_auto_ingested"] = False
        return enriched

    github = client or GitHubAssessmentClient()
    sources: dict[str, dict[str, Any]] = {}

    repo_meta, repo_error = github.get_repo(repository)
    if repo_error or not isinstance(repo_meta, dict):
        sources["repository"] = _source(
            "repository",
            status="unavailable",
            checked_at=checked_at,
            item_count=None,
            note=_safe_provider_note(repo_error),
        )
        enriched["repository"] = repository
        enriched["source_binding"] = {
            "status": "unavailable",
            "repository": repository,
            "checked_at": checked_at,
            "timeframe_days": timeframe_days,
            "baseline": baseline,
            "observed_commit_sha": str(baseline.get("snapshot_commit_sha") or ""),
        }
        enriched["retainer_evidence_sources"] = sources
        enriched["blocker_verification"] = {
            "status": "unverified",
            "checked_sources": [],
            "blocker_count": None,
            "reason": "repository_source_unavailable",
        }
        enriched["technical_evidence_auto_ingested"] = False
        return enriched

    default_branch = str(repo_meta.get("default_branch") or "main")
    sources["repository"] = _source(
        "repository",
        status="verified",
        checked_at=checked_at,
        item_count=1,
        note=f"Default branch {default_branch}; visibility={repo_meta.get('visibility') or 'unknown'}.",
    )

    head_data, head_error = github.get_json(github.repo_url(repository, f"/commits/{default_branch}"))
    observed_commit_sha = ""
    if isinstance(head_data, dict):
        observed_commit_sha = str(head_data.get("sha") or "")
    sources["head_commit"] = _source(
        "head_commit",
        status="verified" if observed_commit_sha else "unavailable",
        checked_at=checked_at,
        item_count=1 if observed_commit_sha else None,
        note=(
            f"Observed {default_branch} head {observed_commit_sha[:12]}."
            if observed_commit_sha
            else _safe_provider_note(head_error)
        ),
    )

    commits, commit_error = github.get_commits(repository, since_iso)
    commit_rows = commits[:MAX_SOURCE_ITEMS]
    sources["commits"] = _source(
        "commits",
        status="verified" if not commit_error else "unavailable",
        checked_at=checked_at,
        item_count=len(commit_rows) if not commit_error else None,
        note=_safe_provider_note(commit_error),
    )

    pulls, pull_error = github.get_pulls(repository, since)
    pull_rows = pulls[:MAX_SOURCE_ITEMS]
    sources["pull_requests"] = _source(
        "pull_requests",
        status="verified" if not pull_error else "unavailable",
        checked_at=checked_at,
        item_count=len(pull_rows) if not pull_error else None,
        note=_safe_provider_note(pull_error),
    )

    issue_data, issue_error = _generic_list(
        github,
        repository,
        "/issues",
        {"state": "all", "since": since_iso, "per_page": MAX_SOURCE_ITEMS, "sort": "updated", "direction": "desc"},
    )
    issue_rows = [item for item in issue_data if "pull_request" not in item][:MAX_SOURCE_ITEMS]
    sources["issues"] = _source(
        "issues",
        status="verified" if not issue_error else "unavailable",
        checked_at=checked_at,
        item_count=len(issue_rows) if not issue_error else None,
        note=_safe_provider_note(issue_error),
    )

    workflows, workflow_error = github.get_workflow_runs(repository, since_iso)
    workflow_rows = workflows[:MAX_SOURCE_ITEMS]
    sources["workflow_runs"] = _source(
        "workflow_runs",
        status="verified" if not workflow_error else "unavailable",
        checked_at=checked_at,
        item_count=len(workflow_rows) if not workflow_error else None,
        note=_safe_provider_note(workflow_error),
    )
    codeql_rows = [
        item
        for item in workflow_rows
        if "codeql" in str(item.get("name") or item.get("display_title") or "").lower()
        or "code scanning" in str(item.get("name") or item.get("display_title") or "").lower()
    ]
    sources["codeql_runs"] = _source(
        "codeql_runs",
        status="verified" if not workflow_error else "unavailable",
        checked_at=checked_at,
        item_count=len(codeql_rows) if not workflow_error else None,
        note=("Derived from verified workflow-run evidence." if not workflow_error else _safe_provider_note(workflow_error)),
        derived_from="workflow_runs",
    )

    release_data, release_error = _generic_list(
        github,
        repository,
        "/releases",
        {"per_page": MAX_SOURCE_ITEMS},
    )
    release_rows = [
        item
        for item in release_data
        if _within_window(item, since, "published_at", "created_at")
    ][:MAX_SOURCE_ITEMS]
    sources["releases"] = _source(
        "releases",
        status="verified" if not release_error else "unavailable",
        checked_at=checked_at,
        item_count=len(release_rows) if not release_error else None,
        note=_safe_provider_note(release_error),
    )

    deployment_data, deployment_error = _generic_list(
        github,
        repository,
        "/deployments",
        {"per_page": MAX_SOURCE_ITEMS},
    )
    deployment_rows = [
        item for item in deployment_data if _within_window(item, since, "created_at", "updated_at")
    ][:MAX_SOURCE_ITEMS]
    sources["deployments"] = _source(
        "deployments",
        status="verified" if not deployment_error else "unavailable",
        checked_at=checked_at,
        item_count=len(deployment_rows) if not deployment_error else None,
        note=(
            "Deployment records verify deployment activity; provider-specific release success remains separately reviewed."
            if not deployment_error
            else _safe_provider_note(deployment_error)
        ),
    )

    blocker_rows: list[str] = []
    issue_blockers = [
        item
        for item in issue_rows
        if str(item.get("state") or "").lower() == "open"
        and bool(set(_labels(item)) & BLOCKER_LABELS)
    ]
    blocker_rows.extend(f"Issue blocker: {_issue_line(item)}" for item in issue_blockers)
    failed_workflows = [
        item
        for item in workflow_rows
        if str(item.get("conclusion") or "").lower() in FAILED_CONCLUSIONS
    ]
    blocker_rows.extend(f"Workflow blocker: {_workflow_line(item)}" for item in failed_workflows)

    blocker_sources_verified = all(
        sources.get(name, {}).get("status") == "verified"
        for name in ("issues", "workflow_runs")
    )
    if blocker_sources_verified:
        blocker_status = "verified_blockers" if blocker_rows else "verified_clear"
        blocker_reason = ""
    else:
        blocker_status = "unverified"
        blocker_reason = "issue_or_workflow_source_unavailable"

    enriched.update(
        {
            "repository": repository,
            "commit_summary": "\n".join(_commit_line(item) for item in commit_rows[:MAX_PUBLIC_ITEMS]),
            "pr_summary": "\n".join(_pull_line(item) for item in pull_rows[:MAX_PUBLIC_ITEMS]),
            "issue_summary": "\n".join(_issue_line(item) for item in issue_rows[:MAX_PUBLIC_ITEMS]),
            "workflow_summary": "\n".join(_workflow_line(item) for item in workflow_rows[:MAX_PUBLIC_ITEMS]),
            "codeql_summary": "\n".join(_workflow_line(item) for item in codeql_rows[:MAX_PUBLIC_ITEMS]),
            "release_notes": "\n".join(_release_line(item) for item in release_rows[:MAX_PUBLIC_ITEMS]),
            "deployment_summary": "\n".join(_deployment_line(item) for item in deployment_rows[:MAX_PUBLIC_ITEMS]),
            "blockers": "\n".join(blocker_rows[:MAX_PUBLIC_ITEMS]),
            "technical_evidence_auto_ingested": True,
            "source_binding": {
                "status": "bound",
                "repository": repository,
                "default_branch": default_branch,
                "observed_commit_sha": observed_commit_sha,
                "checked_at": checked_at,
                "timeframe_days": timeframe_days,
                "timeframe_start": since_iso,
                "baseline": baseline,
            },
            "retainer_evidence_sources": sources,
            "blocker_verification": {
                "status": blocker_status,
                "checked_sources": [
                    name
                    for name in ("issues", "workflow_runs")
                    if sources.get(name, {}).get("status") == "verified"
                ],
                "blocker_count": len(blocker_rows) if blocker_sources_verified else None,
                "reason": blocker_reason,
            },
            "retainer_evidence_metrics": {
                "commits": len(commit_rows),
                "pull_requests": len(pull_rows),
                "issues": len(issue_rows),
                "open_issues": sum(1 for item in issue_rows if str(item.get("state") or "").lower() == "open"),
                "workflow_runs": len(workflow_rows),
                "failed_workflow_runs": len(failed_workflows),
                "codeql_runs": len(codeql_rows),
                "failed_codeql_runs": sum(
                    1
                    for item in codeql_rows
                    if str(item.get("conclusion") or "").lower() in FAILED_CONCLUSIONS
                ),
                "releases": len(release_rows),
                "deployments": len(deployment_rows),
                "blockers": len(blocker_rows),
            },
        }
    )
    enriched["retainer_evidence_ingestion"] = {
        "artifact_schema": RETAINER_EVIDENCE_SCHEMA,
        "status": "complete" if all(item.get("status") == "verified" for item in sources.values()) else "partial",
        "source_binding": deepcopy(enriched["source_binding"]),
        "sources": deepcopy(sources),
        "blocker_verification": deepcopy(enriched["blocker_verification"]),
        "metrics": deepcopy(enriched["retainer_evidence_metrics"]),
        "manual_context_fields": [
            "roadmap_notes",
            "client_update",
            "retainer_metrics",
            "success_metrics",
            "budget_priorities",
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return enriched


__all__ = [
    "RETAINER_EVIDENCE_SCHEMA",
    "DEFAULT_TIMEFRAME_DAYS",
    "MAX_TIMEFRAME_DAYS",
    "BLOCKER_LABELS",
    "FAILED_CONCLUSIONS",
    "resolve_retainer_baseline",
    "build_retainer_evidence_payload",
]
