from __future__ import annotations

import hashlib
import json
import sys
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

VERSION = "nico.comprehensive-assessment-hardening.v1"

_CAPTURED_AT: ContextVar[datetime | None] = ContextVar(
    "nico_assessment_evidence_capture_time",
    default=None,
)
_IMPORT_INSTALLED = False
_FINAL_GATE_INSTALLED = False

_REPORT_GATE_MARKER = "__nico_report_contract_publication_gate_v1__"
_SOURCE_SIGNAL_MARKER = "__nico_source_signal_sample_binding_v1__"
_SNAPSHOT_MARKER = "__nico_frozen_snapshot_operational_evidence_v1__"
_REPORT_VIEW_MARKER = "__nico_review_candidate_report_view_v1__"

_NON_PRODUCTION_MANIFEST_PARTS = {
    ".github",
    "audit-results",
    "benchmark",
    "benchmarks",
    "demo",
    "demos",
    "doc",
    "docs",
    "example",
    "examples",
    "fixture",
    "fixtures",
    "generated",
    "sample",
    "samples",
    "test",
    "tests",
    "vendor",
    "vendors",
}
_GENERATED_MANIFEST_PARTS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}
_DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}

_SCANNER_MARKERS = (
    "osv-scanner",
    "pip-audit",
    "npm-audit",
    "trufflehog",
    "gitleaks",
    "semgrep",
    "bandit",
    "eslint",
    "typescript",
)


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _duration_seconds(started_at: Any, completed_at: Any) -> int | None:
    started = _parse_dt(started_at)
    completed = _parse_dt(completed_at)
    if not started or not completed or completed < started:
        return None
    return max(0, round((completed - started).total_seconds()))


def _safe_note(base_ci: Any, label: str, error: Any) -> str:
    helper = getattr(base_ci, "_safe_note", None)
    if callable(helper):
        return str(helper(label, error))
    return f"{label} was unavailable through the authorized API."


def _job_at_capture(
    base_ci: Any,
    job: Mapping[str, Any],
    run: Mapping[str, Any],
    captured_at: datetime,
) -> dict[str, Any] | None:
    started = _parse_dt(job.get("started_at"))
    completed = _parse_dt(job.get("completed_at"))
    if started and started > captured_at:
        return None

    current_conclusion = _text(job.get("conclusion") or job.get("status") or "unknown", 120)
    if completed and completed <= captured_at:
        conclusion = current_conclusion
        completed_at = job.get("completed_at") or ""
    elif started and started <= captured_at:
        conclusion = "in_progress_at_capture"
        completed_at = ""
    else:
        conclusion = "queued_at_capture"
        completed_at = ""

    started_at = job.get("started_at") or ""
    return {
        "job_id": job.get("id"),
        "run_id": run.get("id"),
        "workflow_name": _text(run.get("name") or run.get("display_title"), 120),
        "workflow_head_sha": _text(run.get("head_sha"), 80).casefold(),
        "job_name": _text(job.get("name"), 120),
        "conclusion": conclusion,
        "current_conclusion_observed_later": (
            current_conclusion if conclusion != current_conclusion else ""
        ),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": _duration_seconds(started_at, completed_at),
        "runner_name": _text(job.get("runner_name"), 80),
        "evidence_cutoff": _iso(captured_at),
        "state_frozen_at_capture": True,
    }


def _collect_workflow_job_evidence_frozen(
    base_ci: Any,
    client: Any,
    repository: str,
    runs: list[dict[str, Any]],
    captured_at: datetime,
) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    unavailable: list[str] = []
    runs_inspected = 0
    max_runs = int(getattr(base_ci, "MAX_RUNS_FOR_JOBS", 20))
    non_success_conclusions = set(
        getattr(
            base_ci,
            "NON_SUCCESS_CONCLUSIONS",
            {"failure", "timed_out", "cancelled", "action_required", "startup_failure"},
        )
    )

    for run in runs[:max_runs]:
        run_id = run.get("id")
        if not run_id:
            continue
        data, error = client.get_json(
            client.repo_url(repository, f"/actions/runs/{run_id}/jobs"),
            {"filter": "latest", "per_page": 100},
        )
        runs_inspected += 1
        if error:
            unavailable.append(_safe_note(base_ci, f"Workflow jobs for run {run_id}", error))
            continue
        run_jobs = data.get("jobs") if isinstance(data, Mapping) else None
        if not isinstance(run_jobs, list):
            unavailable.append(
                f"Workflow jobs for run {run_id} were returned without a jobs list."
            )
            continue
        for raw_job in run_jobs:
            if not isinstance(raw_job, Mapping):
                continue
            frozen = _job_at_capture(base_ci, raw_job, run, captured_at)
            if frozen is not None:
                jobs.append(frozen)

    conclusions = [_text(job.get("conclusion"), 120) or "unknown" for job in jobs]
    successful = sum(value == "success" for value in conclusions)
    non_success = sum(value in non_success_conclusions for value in conclusions)
    skipped = sum(value in {"skipped", "neutral"} for value in conclusions)
    pending = sum(
        value
        in {
            "queued",
            "in_progress",
            "waiting",
            "requested",
            "pending",
            "unknown",
            "queued_at_capture",
            "in_progress_at_capture",
        }
        for value in conclusions
    )
    terminal = successful + non_success
    durations = [
        int(job["duration_seconds"])
        for job in jobs
        if isinstance(job.get("duration_seconds"), int)
    ]
    failed_samples = [
        job for job in jobs if _text(job.get("conclusion")) in non_success_conclusions
    ][:10]
    successful_samples = [
        job for job in jobs if _text(job.get("conclusion")) == "success"
    ][:25]
    pending_samples = [
        job
        for job in jobs
        if _text(job.get("conclusion"))
        in {"queued_at_capture", "in_progress_at_capture"}
    ][:10]
    successful_workflows = sorted(
        {
            _text(job.get("workflow_name"), 120)
            for job in jobs
            if _text(job.get("conclusion")) == "success"
            and _text(job.get("workflow_name"))
        }
    )
    runtime_markers = tuple(getattr(base_ci, "_RUNTIME_PROOF_MARKERS", ()))
    runtime_proof_workflows = [
        name
        for name in successful_workflows
        if any(marker in name.casefold() for marker in runtime_markers)
    ]

    average = round(sum(durations) / len(durations)) if durations else None
    try:
        from statistics import median

        median_duration = round(median(durations)) if durations else None
    except Exception:  # pragma: no cover
        median_duration = None

    return {
        "status": "complete" if jobs and not unavailable else "partial" if jobs else "unavailable",
        "observed_through": _iso(captured_at),
        "runs_inspected": runs_inspected,
        "runs_with_jobs": len({job.get("run_id") for job in jobs if job.get("run_id")}),
        "jobs_observed": len(jobs),
        "successful_jobs": successful,
        "non_success_jobs": non_success,
        "skipped_or_neutral_jobs": skipped,
        "pending_or_unknown_jobs": pending,
        "job_success_rate": round(successful / terminal, 4) if terminal else None,
        "average_job_duration_seconds": average,
        "median_job_duration_seconds": median_duration,
        "successful_workflows": successful_workflows,
        "runtime_proof_workflows": runtime_proof_workflows,
        "runtime_proof_workflow_count": len(runtime_proof_workflows),
        "successful_job_samples": successful_samples,
        "failed_job_samples": failed_samples,
        "pending_job_samples": pending_samples,
        "unavailable_data_notes": sorted(set(unavailable)),
        "state_frozen_at_assessment_start": True,
        "post_capture_job_state_changes_excluded": True,
        "retention_note": (
            "Job states are reconstructed at the immutable assessment capture time. "
            "Later completions and failures are excluded from the frozen assessment, while "
            "current operational monitoring may report them separately."
        ),
    }


def _deployment_status_at_capture(
    statuses: Any,
    captured_at: datetime,
) -> dict[str, Any] | None:
    eligible: list[tuple[datetime, Mapping[str, Any]]] = []
    if isinstance(statuses, list):
        for raw in statuses:
            if not isinstance(raw, Mapping):
                continue
            created = _parse_dt(raw.get("created_at"))
            if created and created <= captured_at:
                eligible.append((created, raw))
    if not eligible:
        return None
    eligible.sort(key=lambda item: item[0], reverse=True)
    return dict(eligible[0][1])


def _collect_deployment_evidence_frozen(
    base_ci: Any,
    client: Any,
    repository: str,
    captured_at: datetime,
) -> dict[str, Any]:
    max_deployments = int(getattr(base_ci, "MAX_DEPLOYMENTS", 10))
    deployments, error = client.get_json(
        client.repo_url(repository, "/deployments"),
        {"per_page": max_deployments},
    )
    if error:
        return {
            "status": "unavailable",
            "observed_through": _iso(captured_at),
            "deployments_observed": 0,
            "environments": [],
            "latest_states": [],
            "unavailable_data_notes": [
                _safe_note(base_ci, "GitHub deployment evidence", error)
            ],
            "state_frozen_at_assessment_start": True,
        }
    if not isinstance(deployments, list):
        return {
            "status": "unavailable",
            "observed_through": _iso(captured_at),
            "deployments_observed": 0,
            "environments": [],
            "latest_states": [],
            "unavailable_data_notes": [
                "GitHub deployment evidence was returned without a deployment list."
            ],
            "state_frozen_at_assessment_start": True,
        }

    eligible_deployments = [
        item
        for item in deployments
        if isinstance(item, Mapping)
        and (
            _parse_dt(item.get("created_at")) is None
            or _parse_dt(item.get("created_at")) <= captured_at
        )
    ][:max_deployments]

    latest_states: list[dict[str, Any]] = []
    unavailable: list[str] = []
    environments: set[str] = set()
    for deployment in eligible_deployments:
        deployment_id = deployment.get("id")
        environment = _text(deployment.get("environment"), 120)
        if environment:
            environments.add(environment)
        state = "pending_at_capture"
        status_created_at = ""
        current_state_observed_later = ""
        if deployment_id:
            statuses, status_error = client.get_json(
                client.repo_url(repository, f"/deployments/{deployment_id}/statuses"),
                {"per_page": 100},
            )
            if status_error:
                unavailable.append(
                    _safe_note(
                        base_ci,
                        f"Deployment status for {deployment_id}",
                        status_error,
                    )
                )
            else:
                selected = _deployment_status_at_capture(statuses, captured_at)
                if selected is not None:
                    state = _text(selected.get("state"), 120) or "unknown_at_capture"
                    status_created_at = _text(selected.get("created_at"), 120)
                elif isinstance(statuses, list) and statuses:
                    current_state_observed_later = _text(
                        (statuses[0] if isinstance(statuses[0], Mapping) else {}).get("state"),
                        120,
                    )

        latest_states.append(
            {
                "deployment_id": deployment_id,
                "environment": environment,
                "ref": _text(deployment.get("ref"), 120),
                "created_at": deployment.get("created_at") or "",
                "latest_state_at_capture": state,
                "latest_state": state,
                "status_created_at": status_created_at,
                "current_state_observed_later": current_state_observed_later,
                "evidence_cutoff": _iso(captured_at),
                "state_frozen_at_capture": True,
            }
        )

    successful = sum(item.get("latest_state") == "success" for item in latest_states)
    failed = sum(
        item.get("latest_state") in {"failure", "error", "inactive"}
        for item in latest_states
    )
    return {
        "status": (
            "complete"
            if eligible_deployments and not unavailable
            else "partial"
            if eligible_deployments
            else "not_observed"
        ),
        "observed_through": _iso(captured_at),
        "deployments_observed": len(eligible_deployments),
        "successful_deployments": successful,
        "non_success_deployments": failed,
        "environments": sorted(environments),
        "latest_states": latest_states,
        "unavailable_data_notes": sorted(set(unavailable)),
        "state_frozen_at_assessment_start": True,
        "post_capture_deployment_state_changes_excluded": True,
        "retention_note": (
            "Deployment states are selected from the latest status timestamp at or before "
            "the assessment capture time. Later status transitions are excluded."
        ),
    }


def _collect_ci_runtime_evidence_frozen(
    client: Any,
    repository: str,
    workflows: dict[str, str],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    from nico import full_assessment_ci_evidence as base_ci

    captured_at = _CAPTURED_AT.get()
    if captured_at is None:
        original = getattr(
            _collect_ci_runtime_evidence_frozen,
            "_nico_original",
            base_ci.collect_ci_runtime_evidence,
        )
        return original(client, repository, workflows, runs)

    jobs = _collect_workflow_job_evidence_frozen(
        base_ci,
        client,
        repository,
        runs,
        captured_at,
    )
    deployments = _collect_deployment_evidence_frozen(
        base_ci,
        client,
        repository,
        captured_at,
    )
    configuration_controls = base_ci.workflow_configuration_controls(workflows)
    return {
        "status": (
            "complete"
            if jobs.get("status") == "complete"
            and deployments.get("status") in {"complete", "not_observed"}
            else "partial"
        ),
        "observed_through": _iso(captured_at),
        "configuration_controls": configuration_controls,
        "job_evidence": jobs,
        "deployment_evidence": deployments,
        "unavailable_data_notes": sorted(
            set(
                (jobs.get("unavailable_data_notes") or [])
                + (deployments.get("unavailable_data_notes") or [])
            )
        ),
        "state_frozen_at_assessment_start": True,
        "mutable_operational_history_affects_technical_score": False,
        "guardrail": (
            "Workflow configuration is exact-SHA evidence. Operational job and deployment "
            "states are frozen at assessment start, reported separately, and have no "
            "technical-score effect."
        ),
    }


def _strict_authoritative_manifests(repo_dir: Path) -> set[str]:
    manifests: set[str] = set()
    for path in repo_dir.rglob("*"):
        if not path.is_file() or path.name not in _DEPENDENCY_FILES:
            continue
        try:
            relative = path.relative_to(repo_dir)
        except ValueError:
            continue
        parts = {part.casefold() for part in relative.parts[:-1]}
        if parts & (_NON_PRODUCTION_MANIFEST_PARTS | _GENERATED_MANIFEST_PARTS):
            continue
        if (
            path.name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
            and not (path.parent / "package.json").is_file()
        ):
            continue
        manifests.add(str(relative).replace("\\", "/"))
    return manifests


def _verified_secret(finding: Mapping[str, Any]) -> bool:
    return bool(
        finding.get("Verified") is True
        or finding.get("verified") is True
        or _text(finding.get("verification_status")).casefold() == "verified"
    )


def _hardened_scanner_projection(
    original: Callable[..., dict[str, Any]],
    tool_name: str,
    payload: Mapping[str, Any],
    raw_blob: Mapping[str, Any] | None,
    workspace: Any,
) -> dict[str, Any]:
    result = original(tool_name, payload, raw_blob, workspace)
    if not isinstance(result, dict):
        return result

    if tool_name == "osv-scanner":
        material = 0
        review_required = 0
        for item in result.get("findings") or []:
            if not isinstance(item, dict):
                continue
            context_complete = item.get("scanner_context_complete") is True
            production_scope_verified = bool(
                item.get("dependency_path")
                and item.get("dependency_path") in set(
                    result.get("authoritative_manifest_paths") or []
                )
            )
            reachability_verified = item.get("reachability_verified") is True
            confirmed_material = bool(
                context_complete
                and production_scope_verified
                and reachability_verified
                and item.get("affected_version_verified") is True
            )
            item.update(
                {
                    "dependency_path_verified": bool(item.get("dependency_path")),
                    "installed_version_verified": bool(item.get("installed_version")),
                    "production_scope_verified": production_scope_verified,
                    "reachability_status": (
                        "verified_reachable"
                        if reachability_verified
                        else "not_verified"
                    ),
                    "material": confirmed_material,
                    "review_required": not confirmed_material,
                    "candidate_classification": (
                        "verified_material_dependency"
                        if confirmed_material
                        else "review_required_dependency_candidate"
                    ),
                    "technical_score_impact": (
                        "material" if confirmed_material else "assurance_only"
                    ),
                }
            )
            material += int(confirmed_material)
            review_required += int(not confirmed_material)
        result["dependency_candidate_disposition"] = {
            "verified_material": material,
            "review_required": review_required,
            "raw_candidate_count": len(
                [item for item in result.get("findings") or [] if isinstance(item, dict)]
            ),
            "production_manifests_only": True,
            "reachability_required_for_materiality": True,
            "raw_artifact_preserved": True,
        }

    if tool_name in {"gitleaks", "trufflehog"}:
        material = 0
        review_required = 0
        for item in result.get("findings") or []:
            if not isinstance(item, dict):
                continue
            confirmed = _verified_secret(item)
            item.update(
                {
                    "material": confirmed,
                    "review_required": not confirmed,
                    "candidate_classification": (
                        "verified_material_secret"
                        if confirmed
                        else "review_required_secret_candidate"
                    ),
                    "technical_score_impact": (
                        "material" if confirmed else "assurance_only"
                    ),
                }
            )
            material += int(confirmed)
            review_required += int(not confirmed)
        disposition = dict(result.get("secret_candidate_disposition") or {})
        disposition.update(
            {
                "verified_material": material,
                "review_required": review_required,
                "raw_candidate_count": (
                    material
                    + review_required
                    + int(result.get("verified_example_placeholder_count") or 0)
                ),
                "verified_candidates_only_are_material": True,
                "raw_artifact_preserved": True,
            }
        )
        result["secret_candidate_disposition"] = disposition

    result["materiality_contract"] = {
        "version": VERSION,
        "candidate_volume_is_not_material_finding_volume": True,
        "production_scope_required": True,
        "exact_dependency_or_source_context_required": True,
        "reachability_or_verification_required_for_materiality": True,
        "unverified_candidates_affect_assurance_only": True,
    }
    return result


def _find_scanner_name(item: Mapping[str, Any]) -> str:
    explicit = _text(
        item.get("scanner_name") or item.get("tool") or item.get("scanner"),
        120,
    ).casefold()
    if explicit:
        return explicit
    haystack = " ".join(
        _text(item.get(key), 1500).casefold()
        for key in ("title", "evidence", "fact", "interpretation", "recommendation")
    )
    for marker in _SCANNER_MARKERS:
        if marker in haystack or marker.replace("-", " ") in haystack:
            return marker
    return "unidentified-scanner"


def _is_review_candidate(item: Mapping[str, Any]) -> bool:
    category = _text(item.get("category"), 80).casefold()
    if category not in {"dependency", "secret", "static", "code"}:
        return False
    if item.get("material") is True:
        return False
    if item.get("review_required") is True:
        return True
    disposition = _text(
        item.get("disposition") or item.get("candidate_classification"),
        200,
    ).casefold()
    if "review" in disposition or "candidate" in disposition:
        return True
    evidence = " ".join(
        _text(item.get(key), 1200).casefold()
        for key in ("evidence", "fact", "title", "interpretation")
    )
    priority = _text(item.get("priority"), 20).upper()
    confidence = _text(item.get("confidence"), 40).casefold()
    return bool(
        "verified=false" in evidence
        or "unverified" in evidence
        or "candidate" in evidence
        or (
            priority in {"P2", "P3"}
            and confidence in {"low", "moderate", "medium", "review limited"}
        )
    )


def _candidate_group(
    category: str,
    scanner: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    identifiers = [
        _text(item.get("finding_id") or item.get("id"), 240)
        for item in records
        if _text(item.get("finding_id") or item.get("id"), 240)
    ]
    locations: list[str] = []
    packages: list[str] = []
    advisories: list[str] = []
    for item in records:
        location = _text(item.get("location"), 500)
        if location and location not in locations:
            locations.append(location)
        package = _text(item.get("package") or item.get("dependency"), 180)
        if package and package not in packages:
            packages.append(package)
        advisory = _text(item.get("advisory_id") or item.get("rule_id"), 180)
        if advisory and advisory not in advisories:
            advisories.append(advisory)

    digest = hashlib.sha256(
        json.dumps(
            {
                "category": category,
                "scanner": scanner,
                "ids": sorted(identifiers),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:12].upper()
    finding_id = f"NICO-CANDIDATE-GROUP-{digest}"
    count = len(records)
    label = {
        "dependency": "Dependency",
        "secret": "Secret",
        "static": "Static-analysis",
        "code": "Code-risk",
    }.get(category, category.title())

    samples: list[str] = []
    if packages:
        samples.append("packages=" + ", ".join(packages[:8]))
    if advisories:
        samples.append("advisories/rules=" + ", ".join(advisories[:8]))
    if locations:
        samples.append("sample locations=" + "; ".join(locations[:6]))

    return {
        "id": finding_id,
        "finding_id": finding_id,
        "source_finding_ids": identifiers,
        "priority": "P2",
        "category": category,
        "status": "review_required",
        "title": f"{label} review candidates from {scanner} ({count} candidates)",
        "location": "; ".join(locations[:8])
        or "Complete candidate locations are retained in the evidence ledger.",
        "fact": (
            f"{count} unverified {category} candidate(s) were retained from {scanner}. "
            "Candidate count is not confirmed defect count. "
            + ("; ".join(samples) if samples else "")
        ).strip(),
        "evidence": (
            f"raw_candidate_count={count}; scanner={scanner}; "
            "full candidate records retained in review_candidate_evidence_register"
        ),
        "interpretation": (
            "These records require exact package/source, production-scope, and "
            "reachability or validity review before any item is promoted to a material finding."
        ),
        "business_impact": (
            "Evidence assurance remains limited until triage, but unverified volume does "
            "not by itself establish client risk or remediation scope."
        ),
        "impact": (
            "Evidence assurance remains limited until triage; no candidate in this group "
            "is represented as a confirmed material defect."
        ),
        "recommendation": (
            "Triage the retained candidate ledger once, promote confirmed items into "
            "individual material findings, and record evidence-backed dismissals for false positives."
        ),
        "confidence": "moderate",
        "owner_role": "Security or platform engineer",
        "effort": "S-M",
        "acceptance_criteria": [
            "Every candidate has an evidence-backed disposition.",
            "Confirmed items are promoted into individual material findings with exact source or dependency paths.",
            "Dismissed items retain a reason and evidence reference.",
        ],
        "cost_of_inaction": "Unresolved assurance limitation; no unsupported monetary claim.",
        "cost_of_inaction_assumptions": [],
        "residual_risk": (
            "Undispositioned candidates may conceal a material issue, but candidate volume "
            "is not treated as defect volume."
        ),
        "roadmap_mappings": [],
        "backlog_issue_mapping": "",
        "material": False,
        "review_required": True,
        "grouped_review_candidate": True,
        "candidate_count": count,
        "technical_score_impact": "assurance_only",
        "full_candidate_details_retained": True,
        "client_detail_pages_generated": 1,
    }


def compress_review_candidates(assessment: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(assessment))
    key = (
        "decision_grade_findings_register"
        if isinstance(output.get("decision_grade_findings_register"), list)
        else "findings_register"
    )
    records = [
        deepcopy(item)
        for item in output.get(key) or []
        if isinstance(item, Mapping)
    ]
    if not records:
        return output

    candidates: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    for item in records:
        if _is_review_candidate(item):
            candidates.append(item)
        else:
            retained.append(item)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in candidates:
        category = _text(item.get("category"), 80).casefold() or "unknown"
        scanner = _find_scanner_name(item)
        groups.setdefault((category, scanner), []).append(item)

    grouped = [
        _candidate_group(category, scanner, items)
        for (category, scanner), items in sorted(groups.items())
    ]
    projected = [*retained, *grouped]
    output[key] = projected
    output["findings_register"] = deepcopy(projected)
    if "decision_grade_findings_register" in output:
        output["decision_grade_findings_register"] = deepcopy(projected)
    output["review_candidate_evidence_register"] = candidates
    output["candidate_presentation_summary"] = {
        "version": VERSION,
        "raw_review_candidate_count": len(candidates),
        "client_candidate_group_count": len(grouped),
        "confirmed_or_non_candidate_finding_count": len(retained),
        "individual_candidate_remediation_pages_suppressed": max(
            0,
            len(candidates) - len(grouped),
        ),
        "full_candidate_records_retained_in_canonical_json": True,
        "full_candidate_records_retained_in_evidence_ledger": True,
        "candidate_volume_is_not_material_finding_volume": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    polish = dict(output.get("comprehensive_report_polish") or {})
    polish.update(
        {
            "review_candidate_categories_grouped": True,
            "dependency_and_secret_candidates_grouped": True,
            "confirmed_material_findings_remain_individual": True,
            "raw_review_candidates_retained": True,
        }
    )
    output["comprehensive_report_polish"] = polish
    return output


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _score_consistency(canonical: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    maturity = (
        assessment.get("maturity_signal")
        if isinstance(assessment.get("maturity_signal"), Mapping)
        else {}
    )
    score_contract = (
        assessment.get("score_contract")
        if isinstance(assessment.get("score_contract"), Mapping)
        else {}
    )
    package = (
        canonical.get("report_package")
        if isinstance(canonical.get("report_package"), Mapping)
        else {}
    )

    technical_values = [
        value
        for value in (
            _numeric(assessment.get("technical_score")),
            _numeric(maturity.get("score")),
            _numeric(maturity.get("source_score")),
            _numeric(maturity.get("presented_score")),
            _numeric(maturity.get("technical_score")),
            _numeric(score_contract.get("technical_score")),
            _numeric(package.get("technical_score")),
        )
        if value is not None
    ]
    adjusted_values = [
        value
        for value in (
            _numeric(assessment.get("canonical_evidence_adjusted_score")),
            _numeric(assessment.get("evidence_adjusted_score")),
            _numeric(maturity.get("canonical_evidence_adjusted_score")),
            _numeric(maturity.get("evidence_adjusted_score")),
            _numeric(score_contract.get("evidence_adjusted_score")),
            _numeric(package.get("canonical_evidence_adjusted_score")),
            _numeric(package.get("evidence_adjusted_score")),
        )
        if value is not None
    ]

    section_mismatches: list[str] = []
    for section in assessment.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        aliases = [
            value
            for value in (
                _numeric(section.get("score")),
                _numeric(section.get("presented_score")),
                _numeric(section.get("score_value")),
            )
            if value is not None
        ]
        if aliases and len({round(value, 8) for value in aliases}) != 1:
            section_mismatches.append(
                _text(section.get("id") or section.get("label"), 180)
                or "unnamed_section"
            )

    technical_consistent = bool(technical_values) and len(
        {round(value, 8) for value in technical_values}
    ) == 1
    adjusted_consistent = bool(adjusted_values) and len(
        {round(value, 8) for value in adjusted_values}
    ) == 1
    consistent = technical_consistent and adjusted_consistent and not section_mismatches
    return consistent, {
        "technical_values": technical_values,
        "evidence_adjusted_values": adjusted_values,
        "technical_aliases_consistent": technical_consistent,
        "evidence_adjusted_aliases_consistent": adjusted_consistent,
        "section_score_mismatches": section_mismatches,
    }


def _iter_mappings(value: Any, depth: int = 0) -> Iterable[dict[str, Any]]:
    if depth > 10:
        return
    if isinstance(value, dict):
        yield value
        for key, child in value.items():
            if str(key).casefold() in {
                "pdf_base64",
                "markdown",
                "html",
                "raw_output",
                "stdout",
                "stderr",
            }:
                continue
            yield from _iter_mappings(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child, depth + 1)


def _contains_score_sync(canonical: Mapping[str, Any]) -> bool:
    return any(
        item.get("final_report_input_scores_synchronized") is True
        for item in _iter_mappings(deepcopy(dict(canonical)))
    )


def _repair_stale_report_contracts_hardened(canonical: dict[str, Any]) -> int:
    if not _contains_score_sync(canonical):
        return 0
    consistent, details = _score_consistency(canonical)
    contract = dict(canonical.get("score_truth_consistency") or {})
    contract.update(
        {
            "version": VERSION,
            **details,
            "consistent": consistent,
            "blocked_contract_reconciliation_allowed": consistent,
        }
    )
    canonical["score_truth_consistency"] = contract
    if not consistent:
        return 0

    repaired = 0
    for item in _iter_mappings(canonical):
        status = _text(item.get("report_contract_status"), 120).casefold()
        reason = _text(item.get("report_contract_reason"), 500).casefold()
        if status != "blocked":
            continue
        if reason not in {
            "canonical_score_truth_mismatch",
            "score_truth_mismatch",
            "canonical_score_mismatch",
        }:
            continue
        item["pre_reconciliation_report_contract"] = {
            "status": item.get("report_contract_status"),
            "reason": item.get("report_contract_reason"),
        }
        item["report_contract_status"] = "reconciled"
        item["report_contract_reason"] = (
            "canonical_score_truth_reconciled_after_value_equality_verification"
        )
        item["report_contract_reconciled"] = True
        item["report_contract_reconciliation_version"] = VERSION
        repaired += 1
    return repaired


def _report_contract_blocks(value: Any) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []

    def visit(current: Any, path: str, depth: int) -> None:
        if depth > 10:
            return
        if isinstance(current, Mapping):
            status = _text(current.get("report_contract_status"), 120).casefold()
            if status == "blocked":
                blocks.append(
                    {
                        "path": path or "root",
                        "reason": _text(
                            current.get("report_contract_reason")
                            or current.get("reason")
                            or "unspecified_report_contract_block",
                            500,
                        ),
                    }
                )
            for key, child in current.items():
                if str(key).casefold() in {
                    "pdf_base64",
                    "markdown",
                    "html",
                    "raw_output",
                    "stdout",
                    "stderr",
                }:
                    continue
                visit(child, f"{path}.{key}" if path else str(key), depth + 1)
        elif isinstance(current, list):
            for index, child in enumerate(current):
                visit(child, f"{path}[{index}]", depth + 1)

    visit(value, "", 0)
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for block in blocks:
        marker = (block["path"], block["reason"])
        if marker not in seen:
            seen.add(marker)
            unique.append(block)
    return unique


def enforce_report_contract_gate(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    output = deepcopy(result)
    blocks = _report_contract_blocks(
        {
            "assessment": output.get("assessment"),
            "stage_summaries": output.get("stage_summaries"),
            "report_package_json": (
                (output.get("report_package") or {}).get("json")
                if isinstance(output.get("report_package"), Mapping)
                else None
            ),
        }
    )
    quality = dict(output.get("report_quality_contract") or {})
    quality.update(
        {
            "report_contract_publication_gate_version": VERSION,
            "report_contract_blocked_count": len(blocks),
            "report_contracts_clear": not blocks,
            "blocked_report_contracts": blocks,
        }
    )
    output["report_quality_contract"] = quality

    package = (
        deepcopy(dict(output.get("report_package") or {}))
        if isinstance(output.get("report_package"), Mapping)
        else {}
    )
    package_quality = dict(package.get("report_quality_contract") or {})
    package_quality.update(quality)
    package["report_quality_contract"] = package_quality
    package["report_contract_status"] = "blocked" if blocks else "clear"
    package["human_review_required"] = True
    package["client_delivery_allowed"] = False

    if blocks:
        primary_reason = blocks[0]["reason"] or "unspecified_report_contract_block"
        output["status"] = "blocked"
        output["reason"] = f"report_contract_blocked:{primary_reason}"
        output["report_contract_status"] = "blocked"
        output["report_contract_reason"] = primary_reason
        output["delivery_status"] = "Delivery Blocked"
        output["human_review_required"] = True
        output["client_delivery_allowed"] = False
        package["delivery_status"] = "Delivery Blocked"
        package["publication_allowed"] = False
        package["complete"] = False
    else:
        output["report_contract_status"] = "clear"
        package["publication_allowed"] = output.get("status") == "complete"
    output["report_package"] = package
    return output


def _wrap_report_builder(delegate: Callable[..., Any]) -> Callable[..., Any]:
    if getattr(delegate, _REPORT_GATE_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return enforce_report_contract_gate(delegate(*args, **kwargs))

    setattr(wrapped, _REPORT_GATE_MARKER, True)
    return wrapped


def _wrap_report_view(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _REPORT_VIEW_MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(assessment: dict[str, Any], contract: Any) -> dict[str, Any]:
        return compress_review_candidates(delegate(assessment, contract))

    setattr(wrapped, _REPORT_VIEW_MARKER, True)
    return wrapped


def _install_source_signal_binding() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_v5 as decision_grade
    from nico import snapshot_repository_evidence as snapshot

    current = snapshot.analyze_source_signals
    if not getattr(current, _SOURCE_SIGNAL_MARKER, False):
        original = current

        @wraps(original)
        def analyze(files: Mapping[str, str]) -> dict[str, Any]:
            result = original(files)
            decision_grade._SCAN_DETAILS.set(
                {
                    "risk_pattern_samples": list(result.get("risks") or [])[:20],
                    "potential_secret_pattern_samples": list(result.get("secrets") or [])[:20],
                    "todo_fixme_security_samples": list(result.get("todos") or [])[:20],
                }
            )
            return result

        setattr(analyze, _SOURCE_SIGNAL_MARKER, True)
        snapshot.analyze_source_signals = analyze
        current = analyze

    snapshot.scan_files = current
    return {
        "source_signal_binding_compatible": True,
        "scan_files_compatibility_alias_bound": snapshot.scan_files is current,
        "executable_source_analyzer_remains_authoritative": True,
    }


def _install_frozen_operational_evidence() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_v5 as decision_grade
    from nico import snapshot_repository_evidence as snapshot

    current_collect = snapshot.collect_snapshot_repository_evidence
    if getattr(current_collect, _SNAPSHOT_MARKER, False):
        decision_grade._ORIGINAL_COLLECT = current_collect
        return {
            "frozen_operational_evidence_bound": True,
            "state_frozen_at_assessment_start": True,
        }

    original_collect = current_collect
    original_ci = snapshot.collect_ci_runtime_evidence
    setattr(_collect_ci_runtime_evidence_frozen, "_nico_original", original_ci)
    snapshot.collect_ci_runtime_evidence = _collect_ci_runtime_evidence_frozen

    @wraps(original_collect)
    def collect(
        context: dict[str, Any],
        evidence_snapshot: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        captured_at = _parse_dt(evidence_snapshot.get("captured_at"))
        token = _CAPTURED_AT.set(captured_at)
        try:
            return original_collect(context, evidence_snapshot, *args, **kwargs)
        finally:
            _CAPTURED_AT.reset(token)

    setattr(collect, _SNAPSHOT_MARKER, True)
    snapshot.collect_snapshot_repository_evidence = collect
    decision_grade._ORIGINAL_COLLECT = collect
    return {
        "frozen_operational_evidence_bound": True,
        "state_frozen_at_assessment_start": True,
        "post_capture_job_state_changes_excluded": True,
        "post_capture_deployment_state_changes_excluded": True,
    }


def _install_scanner_materiality_hardening() -> dict[str, Any]:
    from nico import scanner_result_truth_v1 as scanner_truth

    scanner_truth._authoritative_manifests = _strict_authoritative_manifests
    current = scanner_truth.reconcile_scanner_payload
    if not getattr(current, "__nico_materiality_hardening_v1__", False):
        original = current

        @wraps(original)
        def reconcile(
            tool_name: str,
            payload: Mapping[str, Any],
            raw_blob: Mapping[str, Any] | None,
            workspace: Any,
        ) -> dict[str, Any]:
            return _hardened_scanner_projection(
                original,
                tool_name,
                payload,
                raw_blob,
                workspace,
            )

        setattr(reconcile, "__nico_materiality_hardening_v1__", True)
        scanner_truth.reconcile_scanner_payload = reconcile
        current = reconcile

    authority = sys.modules.get("nico.v2_snapshot_scanner_authority")
    if authority is not None:
        authority.reconcile_scanner_payload = current

    return {
        "production_manifest_scope_filter_bound": True,
        "non_production_manifests_excluded": True,
        "reachability_required_for_dependency_materiality": True,
        "verified_secret_required_for_secret_materiality": True,
        "candidate_volume_is_not_material_finding_volume": True,
    }


def _install_score_truth_reconciliation() -> dict[str, Any]:
    from nico import client_assessment_truth_v3 as truth

    truth._repair_stale_report_contracts = _repair_stale_report_contracts_hardened
    return {
        "score_mismatch_reconciliation_requires_value_equality": True,
        "inconsistent_score_contract_remains_blocked": True,
    }


def _install_candidate_presentation() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico import comprehensive_report_polish_v1 as polish

    original_polish = polish.polish_assessment
    if not getattr(original_polish, "__nico_candidate_presentation_v1__", False):

        @wraps(original_polish)
        def enhanced(assessment: dict[str, Any]) -> dict[str, Any]:
            return compress_review_candidates(original_polish(assessment))

        setattr(enhanced, "__nico_candidate_presentation_v1__", True)
        polish.polish_assessment = enhanced

    report.apply_report_view = _wrap_report_view(report.apply_report_view)
    return {
        "review_candidate_summary_bound": True,
        "dependency_and_secret_candidate_pages_grouped": True,
        "confirmed_material_findings_remain_individual": True,
        "full_candidate_records_retained": True,
    }


def _install_base_report_gate() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    report.build_comprehensive_report_package = _wrap_report_builder(
        report.build_comprehensive_report_package
    )
    return {
        "base_report_contract_publication_gate_bound": True,
        "blocked_contract_cannot_publish_complete": True,
    }


def install_import_time_hardening() -> dict[str, Any]:
    global _IMPORT_INSTALLED
    source = _install_source_signal_binding()
    frozen = _install_frozen_operational_evidence()
    scanner = _install_scanner_materiality_hardening()
    score_truth = _install_score_truth_reconciliation()
    candidates = _install_candidate_presentation()
    report_gate = _install_base_report_gate()
    _IMPORT_INSTALLED = True
    return {
        "version": VERSION,
        "installed": True,
        **source,
        **frozen,
        **scanner,
        **score_truth,
        **candidates,
        **report_gate,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_final_publisher_gate() -> dict[str, Any]:
    global _FINAL_GATE_INSTALLED
    from nico import comprehensive_decision_grade_v5 as decision_grade
    from nico import comprehensive_native_providers as providers
    from nico import comprehensive_report_appendix_v3 as appendix

    providers.build_comprehensive_report_package = _wrap_report_builder(
        providers.build_comprehensive_report_package
    )
    decision_grade.build_comprehensive_report_package = _wrap_report_builder(
        decision_grade.build_comprehensive_report_package
    )
    appendix.build_comprehensive_report_package = _wrap_report_builder(
        appendix.build_comprehensive_report_package
    )
    _FINAL_GATE_INSTALLED = True
    return {
        "version": VERSION,
        "final_report_contract_publication_gate_bound": True,
        "providers_gate_bound": getattr(
            providers.build_comprehensive_report_package,
            _REPORT_GATE_MARKER,
            False,
        ),
        "decision_grade_gate_bound": getattr(
            decision_grade.build_comprehensive_report_package,
            _REPORT_GATE_MARKER,
            False,
        ),
        "appendix_gate_bound": getattr(
            appendix.build_comprehensive_report_package,
            _REPORT_GATE_MARKER,
            False,
        ),
        "blocked_contract_cannot_publish_complete": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "compress_review_candidates",
    "enforce_report_contract_gate",
    "install_final_publisher_gate",
    "install_import_time_hardening",
]
