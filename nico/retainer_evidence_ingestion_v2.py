from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime
from typing import Any

from nico.hosted_assessment import GitHubAssessmentClient
from nico.retainer_evidence_ingestion import (
    BLOCKER_LABELS,
    FAILED_CONCLUSIONS,
    MAX_PUBLIC_ITEMS,
    MAX_SOURCE_ITEMS,
    build_retainer_evidence_payload,
)

RETAINER_EVIDENCE_V2_SCHEMA = "nico.retainer_evidence_ingestion.v2"
TECHNICAL_FIELDS = (
    "commit_summary",
    "pr_summary",
    "issue_summary",
    "workflow_summary",
    "codeql_summary",
    "release_notes",
    "deployment_summary",
    "blockers",
)


def _safe_note(error: str | None) -> str:
    if not error:
        return ""
    match = re.search(r"returned\s+(\d{3})", str(error), flags=re.IGNORECASE)
    if match:
        return f"GitHub source returned HTTP {match.group(1)}."
    return "GitHub source was unavailable during this evidence refresh."


def _labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for raw in item.get("labels") or []:
        if isinstance(raw, dict):
            value = str(raw.get("name") or "").strip().lower()
        else:
            value = str(raw or "").strip().lower()
        if value:
            labels.append(value)
    return labels


def _issue_line(item: dict[str, Any]) -> str:
    number = item.get("number")
    title = str(item.get("title") or "Untitled issue").strip()
    labels = ", ".join(_labels(item)) or "no labels"
    updated = str(item.get("updated_at") or item.get("created_at") or "")
    return f"Issue #{number} · open · {title} · labels={labels} · {updated or 'time unavailable'}"


def _workflow_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("workflow_id") or item.get("display_title") or "unknown-workflow")


def _workflow_line(item: dict[str, Any]) -> str:
    name = _workflow_name(item)
    conclusion = str(item.get("conclusion") or item.get("status") or "unknown")
    event = str(item.get("event") or "unknown")
    created = str(item.get("created_at") or "")
    head_sha = str(item.get("head_sha") or "")[:12]
    return f"{name} · {conclusion} · event={event} · sha={head_sha or 'unavailable'} · {created or 'time unavailable'}"


def _latest_by_workflow(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    ordered = sorted(
        rows,
        key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""),
        reverse=True,
    )
    for item in ordered:
        latest.setdefault(_workflow_name(item), item)
    return list(latest.values())


def _fail_closed_explicit_baseline(
    payload: dict[str, Any],
    enriched: dict[str, Any],
) -> dict[str, Any] | None:
    requested_run_id = str(payload.get("baseline_run_id") or "").strip()
    if not requested_run_id:
        return None
    binding = enriched.get("source_binding") if isinstance(enriched.get("source_binding"), dict) else {}
    baseline = binding.get("baseline") if isinstance(binding.get("baseline"), dict) else {}
    if (
        str(baseline.get("status") or "") == "matched"
        and str(baseline.get("run_id") or "") == requested_run_id
    ):
        return None

    failed = deepcopy(payload)
    repository = str(binding.get("repository") or payload.get("repository") or "")
    checked_at = str(binding.get("checked_at") or "")
    for field in TECHNICAL_FIELDS:
        failed[field] = ""
    failed.update(
        {
            "repository": repository,
            "source_binding": {
                "status": "baseline_mismatch",
                "repository": repository,
                "checked_at": checked_at,
                "timeframe_days": binding.get("timeframe_days") or payload.get("timeframe_days"),
                "observed_commit_sha": "",
                "baseline": {
                    "status": "not_matched",
                    "baseline_type": "explicit_run",
                    "requested_run_id": requested_run_id,
                    "run_id": "",
                    "snapshot_id": "",
                    "snapshot_commit_sha": "",
                    "scanner_id": "",
                },
            },
            "retainer_evidence_sources": {},
            "retainer_evidence_metrics": {},
            "blocker_verification": {
                "status": "unverified",
                "checked_sources": [],
                "blocker_count": None,
                "reason": "explicit_baseline_not_matched",
            },
            "technical_evidence_auto_ingested": False,
            "retainer_evidence_ingestion": {
                "artifact_schema": RETAINER_EVIDENCE_V2_SCHEMA,
                "status": "blocked",
                "code": "explicit_baseline_not_matched",
                "requested_run_id": requested_run_id,
                "sources": {},
                "blocker_verification": {
                    "status": "unverified",
                    "checked_sources": [],
                    "blocker_count": None,
                    "reason": "explicit_baseline_not_matched",
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        }
    )
    return failed


def build_retainer_evidence_payload_v2(
    payload: dict[str, Any],
    *,
    latest_express: dict[str, Any] | None = None,
    latest_mid: dict[str, Any] | None = None,
    store: Any = None,
    client: GitHubAssessmentClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    github = client or GitHubAssessmentClient()
    enriched = build_retainer_evidence_payload(
        payload,
        latest_express=latest_express,
        latest_mid=latest_mid,
        store=store,
        client=github,
        now=now,
    )
    explicit_failure = _fail_closed_explicit_baseline(payload, enriched)
    if explicit_failure is not None:
        return explicit_failure

    binding = enriched.get("source_binding") if isinstance(enriched.get("source_binding"), dict) else {}
    repository = str(binding.get("repository") or enriched.get("repository") or "")
    if str(binding.get("status") or "") != "bound" or not repository:
        ingestion = enriched.get("retainer_evidence_ingestion") if isinstance(enriched.get("retainer_evidence_ingestion"), dict) else {}
        ingestion["artifact_schema"] = RETAINER_EVIDENCE_V2_SCHEMA
        enriched["retainer_evidence_ingestion"] = ingestion
        return enriched

    checked_at = str(binding.get("checked_at") or "")
    sources = deepcopy(enriched.get("retainer_evidence_sources") or {})
    metrics = deepcopy(enriched.get("retainer_evidence_metrics") or {})

    open_data, open_error = github.get_json(
        github.repo_url(repository, "/issues"),
        {
            "state": "open",
            "per_page": MAX_SOURCE_ITEMS,
            "sort": "updated",
            "direction": "desc",
        },
    )
    if isinstance(open_data, list) and not open_error:
        open_issues = [
            item
            for item in open_data
            if isinstance(item, dict) and "pull_request" not in item
        ][:MAX_SOURCE_ITEMS]
        sources["open_issues"] = {
            "source_id": "open_issues",
            "status": "verified",
            "checked_at": checked_at,
            "item_count": len(open_issues),
            "note": "Current open issues were checked without a timeframe cutoff.",
            "derived_from": "",
        }
    else:
        open_issues = []
        sources["open_issues"] = {
            "source_id": "open_issues",
            "status": "unavailable",
            "checked_at": checked_at,
            "item_count": None,
            "note": _safe_note(open_error),
            "derived_from": "",
        }

    timeframe_start = str(binding.get("timeframe_start") or "")
    workflow_rows, workflow_error = github.get_workflow_runs(repository, timeframe_start)
    latest_workflows = _latest_by_workflow(
        [item for item in workflow_rows if isinstance(item, dict)]
    ) if not workflow_error else []
    failed_latest = [
        item
        for item in latest_workflows
        if str(item.get("conclusion") or "").lower() in FAILED_CONCLUSIONS
    ]
    latest_codeql = [
        item
        for item in latest_workflows
        if "codeql" in _workflow_name(item).lower()
        or "code scanning" in _workflow_name(item).lower()
    ]
    failed_latest_codeql = [
        item
        for item in latest_codeql
        if str(item.get("conclusion") or "").lower() in FAILED_CONCLUSIONS
    ]
    sources["latest_workflow_state"] = {
        "source_id": "latest_workflow_state",
        "status": "verified" if not workflow_error else "unavailable",
        "checked_at": checked_at,
        "item_count": len(latest_workflows) if not workflow_error else None,
        "note": (
            "Only the newest observed run for each workflow is used for current blocker verification."
            if not workflow_error
            else _safe_note(workflow_error)
        ),
        "derived_from": "workflow_runs",
    }

    issue_blockers = [
        item
        for item in open_issues
        if bool(set(_labels(item)) & BLOCKER_LABELS)
    ]
    blockers = [f"Issue blocker: {_issue_line(item)}" for item in issue_blockers]
    blockers.extend(
        f"Workflow blocker: {_workflow_line(item)}"
        for item in failed_latest
    )

    required_verified = (
        sources.get("open_issues", {}).get("status") == "verified"
        and sources.get("latest_workflow_state", {}).get("status") == "verified"
    )
    blocker_status = (
        "verified_blockers"
        if required_verified and blockers
        else "verified_clear"
        if required_verified
        else "unverified"
    )
    enriched["blockers"] = "\n".join(blockers[:MAX_PUBLIC_ITEMS])
    enriched["blocker_verification"] = {
        "status": blocker_status,
        "checked_sources": [
            source_id
            for source_id in ("open_issues", "latest_workflow_state")
            if sources.get(source_id, {}).get("status") == "verified"
        ],
        "blocker_count": len(blockers) if required_verified else None,
        "reason": "" if required_verified else "open_issue_or_latest_workflow_source_unavailable",
        "rule": "Current blocker state uses all open labeled issues and only the newest observed run for each workflow.",
    }
    metrics["open_issues"] = len(open_issues) if sources["open_issues"]["status"] == "verified" else None
    metrics["failed_workflow_runs"] = len(failed_latest) if not workflow_error else None
    metrics["failed_codeql_runs"] = len(failed_latest_codeql) if not workflow_error else None
    metrics["blockers"] = len(blockers) if required_verified else None
    enriched["retainer_evidence_sources"] = sources
    enriched["retainer_evidence_metrics"] = metrics

    current_issue_lines = [_issue_line(item) for item in open_issues[:MAX_PUBLIC_ITEMS]]
    recent_issue_lines = [
        line
        for line in str(enriched.get("issue_summary") or "").splitlines()
        if line.strip()
    ]
    enriched["issue_summary"] = "\n".join(
        list(dict.fromkeys(current_issue_lines + recent_issue_lines))[:MAX_PUBLIC_ITEMS]
    )

    ingestion = enriched.get("retainer_evidence_ingestion") if isinstance(enriched.get("retainer_evidence_ingestion"), dict) else {}
    ingestion.update(
        {
            "artifact_schema": RETAINER_EVIDENCE_V2_SCHEMA,
            "sources": deepcopy(sources),
            "blocker_verification": deepcopy(enriched["blocker_verification"]),
            "metrics": deepcopy(metrics),
            "current_state_rule": "Open issue blockers are checked without a timeframe cutoff; workflow blockers use the newest run per workflow.",
        }
    )
    ingestion["status"] = (
        "complete"
        if all(
            source.get("status") == "verified"
            for source in sources.values()
            if isinstance(source, dict)
        )
        else "partial"
    )
    enriched["retainer_evidence_ingestion"] = ingestion
    return enriched


__all__ = [
    "RETAINER_EVIDENCE_V2_SCHEMA",
    "build_retainer_evidence_payload_v2",
]
