from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

MAX_RUNS_FOR_JOBS = 20
MAX_DEPLOYMENTS = 10
NON_SUCCESS_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_seconds(started_at: Any, completed_at: Any) -> int | None:
    started = _parse_dt(started_at)
    completed = _parse_dt(completed_at)
    if not started or not completed or completed < started:
        return None
    return max(0, round((completed - started).total_seconds()))


def _safe_note(label: str, error: Any) -> str:
    lowered = str(error or "").lower()
    if "401" in lowered or "403" in lowered:
        return f"{label} was unavailable because the GitHub credential or installation lacks required read access."
    if "404" in lowered:
        return f"{label} was unavailable through the authorized GitHub API scope."
    if "429" in lowered or "rate" in lowered:
        return f"{label} was unavailable because the GitHub API rate limit was reached."
    return f"{label} was unavailable through the GitHub API."


def workflow_configuration_controls(workflows: dict[str, str]) -> dict[str, Any]:
    combined = "\n".join(str(value) for value in workflows.values()).lower()
    controls = {
        "cache": "actions/cache" in combined or "cache:" in combined,
        "concurrency": "concurrency:" in combined,
        "timeout": "timeout-minutes:" in combined,
        "matrix": "matrix:" in combined,
        "artifact_upload": "actions/upload-artifact" in combined,
        "environment_gate": "environment:" in combined,
        "test_command": any(marker in combined for marker in ("pytest", "npm test", "pnpm test", "yarn test")),
        "lint_command": any(marker in combined for marker in ("npm run lint", "pnpm lint", "yarn lint", "eslint", "ruff", "flake8")),
        "build_command": any(marker in combined for marker in ("npm run build", "pnpm build", "yarn build", "next build", "docker build")),
        "security_command": any(marker in combined for marker in ("semgrep", "bandit", "codeql", "pip-audit", "npm audit", "osv-scanner", "gitleaks")),
        "deployment_command": any(marker in combined for marker in ("deploy", "vercel", "railway", "render", "kubectl", "terraform", "docker push")),
    }
    return {
        **controls,
        "control_count": sum(1 for value in controls.values() if value),
    }


def _job_summary(job: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job.get("id"),
        "run_id": run.get("id"),
        "workflow_name": str(run.get("name") or run.get("display_title") or "")[:120],
        "job_name": str(job.get("name") or "")[:120],
        "conclusion": job.get("conclusion") or job.get("status") or "unknown",
        "started_at": job.get("started_at") or "",
        "completed_at": job.get("completed_at") or "",
        "duration_seconds": _duration_seconds(job.get("started_at"), job.get("completed_at")),
        "runner_name": str(job.get("runner_name") or "")[:80],
    }


def collect_workflow_job_evidence(client: Any, repository: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    unavailable: list[str] = []
    runs_inspected = 0

    for run in runs[:MAX_RUNS_FOR_JOBS]:
        run_id = run.get("id")
        if not run_id:
            continue
        data, error = client.get_json(
            client.repo_url(repository, f"/actions/runs/{run_id}/jobs"),
            {"filter": "latest", "per_page": 100},
        )
        runs_inspected += 1
        if error:
            unavailable.append(_safe_note(f"Workflow jobs for run {run_id}", error))
            continue
        run_jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(run_jobs, list):
            unavailable.append(f"Workflow jobs for run {run_id} were returned without a jobs list.")
            continue
        jobs.extend(_job_summary(job, run) for job in run_jobs if isinstance(job, dict))

    conclusions = [str(job.get("conclusion") or "unknown") for job in jobs]
    successful = sum(1 for value in conclusions if value == "success")
    non_success = sum(1 for value in conclusions if value in NON_SUCCESS_CONCLUSIONS)
    skipped = sum(1 for value in conclusions if value in {"skipped", "neutral"})
    pending = sum(1 for value in conclusions if value in {"queued", "in_progress", "waiting", "requested", "pending", "unknown"})
    terminal = successful + non_success
    durations = [int(job["duration_seconds"]) for job in jobs if isinstance(job.get("duration_seconds"), int)]
    failed_samples = [job for job in jobs if str(job.get("conclusion")) in NON_SUCCESS_CONCLUSIONS][:10]

    return {
        "status": "complete" if jobs and not unavailable else "partial" if jobs else "unavailable",
        "runs_inspected": runs_inspected,
        "runs_with_jobs": len({job.get("run_id") for job in jobs if job.get("run_id")}),
        "jobs_observed": len(jobs),
        "successful_jobs": successful,
        "non_success_jobs": non_success,
        "skipped_or_neutral_jobs": skipped,
        "pending_or_unknown_jobs": pending,
        "job_success_rate": round(successful / terminal, 4) if terminal else None,
        "average_job_duration_seconds": round(sum(durations) / len(durations)) if durations else None,
        "median_job_duration_seconds": round(median(durations)) if durations else None,
        "failed_job_samples": failed_samples,
        "unavailable_data_notes": sorted(set(unavailable)),
        "retention_note": "Job names, conclusions, timestamps, and bounded duration summaries are retained; job logs and secrets are not collected.",
    }


def collect_deployment_evidence(client: Any, repository: str) -> dict[str, Any]:
    deployments, error = client.get_json(
        client.repo_url(repository, "/deployments"),
        {"per_page": MAX_DEPLOYMENTS},
    )
    if error:
        return {
            "status": "unavailable",
            "deployments_observed": 0,
            "environments": [],
            "latest_states": [],
            "unavailable_data_notes": [_safe_note("GitHub deployment evidence", error)],
        }
    if not isinstance(deployments, list):
        return {
            "status": "unavailable",
            "deployments_observed": 0,
            "environments": [],
            "latest_states": [],
            "unavailable_data_notes": ["GitHub deployment evidence was returned without a deployment list."],
        }

    latest_states: list[dict[str, Any]] = []
    unavailable: list[str] = []
    environments: set[str] = set()
    for deployment in deployments[:MAX_DEPLOYMENTS]:
        if not isinstance(deployment, dict):
            continue
        deployment_id = deployment.get("id")
        environment = str(deployment.get("environment") or "")[:120]
        if environment:
            environments.add(environment)
        state = "unknown"
        if deployment_id:
            statuses, status_error = client.get_json(
                client.repo_url(repository, f"/deployments/{deployment_id}/statuses"),
                {"per_page": 1},
            )
            if status_error:
                unavailable.append(_safe_note(f"Deployment status for {deployment_id}", status_error))
            elif isinstance(statuses, list) and statuses:
                state = str(statuses[0].get("state") or "unknown")
        latest_states.append(
            {
                "deployment_id": deployment_id,
                "environment": environment,
                "ref": str(deployment.get("ref") or "")[:120],
                "created_at": deployment.get("created_at") or "",
                "latest_state": state,
            }
        )

    successful = sum(1 for item in latest_states if item.get("latest_state") == "success")
    failed = sum(1 for item in latest_states if item.get("latest_state") in {"failure", "error", "inactive"})
    return {
        "status": "complete" if deployments and not unavailable else "partial" if deployments else "not_observed",
        "deployments_observed": len(deployments),
        "successful_deployments": successful,
        "non_success_deployments": failed,
        "environments": sorted(environments),
        "latest_states": latest_states,
        "unavailable_data_notes": sorted(set(unavailable)),
        "retention_note": "Deployment identifiers, environment names, refs, timestamps, and latest states are retained; deployment logs and environment secrets are not collected.",
    }


def collect_ci_runtime_evidence(
    client: Any,
    repository: str,
    workflows: dict[str, str],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    jobs = collect_workflow_job_evidence(client, repository, runs)
    deployments = collect_deployment_evidence(client, repository)
    return {
        "status": "complete" if jobs.get("status") == "complete" and deployments.get("status") in {"complete", "not_observed"} else "partial",
        "configuration_controls": workflow_configuration_controls(workflows),
        "job_evidence": jobs,
        "deployment_evidence": deployments,
        "unavailable_data_notes": sorted(
            set((jobs.get("unavailable_data_notes") or []) + (deployments.get("unavailable_data_notes") or []))
        ),
        "guardrail": "CI score credit is based on attached workflow configuration, job conclusions, durations, and deployment states. Logs are not collected and successful execution does not prove defect-free software.",
    }
