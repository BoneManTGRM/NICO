from __future__ import annotations

from typing import Any

from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS, full_assessment_scoring_handler


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and item.get("id")
    }


def _append_unique(values: list[Any], line: str) -> None:
    if line not in values:
        values.append(line)


def _recompute_technical_score(assessment: dict[str, Any]) -> None:
    sections = _section_map(assessment)
    weighted = 0
    total = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = sections.get(section_id)
        if not section or section.get("status") == "gray":
            continue
        weighted += _int(section.get("score")) * weight
        total += weight
    score = round(weighted / total) if total else 0
    level = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    signal = assessment.setdefault("maturity_signal", {})
    signal["score"] = score
    signal["level"] = level
    signal["summary"] = "Weighted technical score includes attached job-level CI evidence without changing section weights."
    scorecard = assessment.setdefault("scorecard", {})
    scorecard["technical_score"] = score
    scorecard["weights"] = TECHNICAL_SECTION_WEIGHTS
    scorecard["ci_job_evidence_applied"] = True


def apply_ci_runtime_score(assessment: dict[str, Any], repository_evidence: dict[str, Any]) -> dict[str, Any]:
    """Apply bounded CI credit only when job-level evidence is attached."""

    workflows = _dict(repository_evidence.get("workflow_evidence"))
    jobs = _dict(workflows.get("job_evidence"))
    controls = _dict(workflows.get("configuration_controls"))
    deployments = _dict(workflows.get("deployment_evidence"))
    observed = _int(jobs.get("jobs_observed"))
    if observed <= 0 or jobs.get("status") not in {"complete", "partial"}:
        assessment.setdefault("scorecard", {})["ci_job_evidence_applied"] = False
        return assessment

    ci_section = _section_map(assessment).get("ci_cd")
    if not ci_section:
        return assessment

    baseline = _int(ci_section.get("score"))
    increment = 0
    reasons: list[str] = []

    runs_with_jobs = _int(jobs.get("runs_with_jobs"))
    success_rate = _float(jobs.get("job_success_rate"))
    successful_jobs = _int(jobs.get("successful_jobs"))
    non_success_jobs = _int(jobs.get("non_success_jobs"))
    median_duration = jobs.get("median_job_duration_seconds")

    increment += 4
    reasons.append(f"+4 attached job-level evidence across {observed} observed job(s)")

    if runs_with_jobs >= 5:
        increment += 2
        reasons.append(f"+2 job evidence spans {runs_with_jobs} workflow run(s)")
    elif runs_with_jobs >= 2:
        increment += 1
        reasons.append(f"+1 job evidence spans {runs_with_jobs} workflow run(s)")

    if success_rate is not None:
        if success_rate >= 0.95:
            increment += 5
            reasons.append(f"+5 terminal job success rate is {success_rate:.1%}")
        elif success_rate >= 0.85:
            increment += 3
            reasons.append(f"+3 terminal job success rate is {success_rate:.1%}")
        elif success_rate >= 0.70:
            increment += 1
            reasons.append(f"+1 terminal job success rate is {success_rate:.1%}")
        elif non_success_jobs > successful_jobs:
            increment -= 4
            reasons.append("-4 non-success jobs outnumber successful jobs")

    operational_controls = [
        name
        for name in ("cache", "concurrency", "timeout", "matrix", "artifact_upload", "environment_gate")
        if controls.get(name) is True
    ]
    control_credit = min(4, len(operational_controls))
    if control_credit:
        increment += control_credit
        reasons.append(f"+{control_credit} operational workflow control(s): {', '.join(operational_controls)}")

    deployments_observed = _int(deployments.get("deployments_observed"))
    successful_deployments = _int(deployments.get("successful_deployments"))
    non_success_deployments = _int(deployments.get("non_success_deployments"))
    if deployments_observed and successful_deployments:
        increment += 2
        reasons.append(f"+2 GitHub deployment evidence includes {successful_deployments} successful deployment(s)")
    if non_success_deployments > successful_deployments and non_success_deployments:
        increment -= 2
        reasons.append("-2 non-success deployment states outnumber successful deployment states")

    score = max(0, min(95, baseline + increment))
    ci_section["score"] = score
    ci_section["status"] = "green" if score >= 80 else "yellow" if score >= 55 else "red"
    ci_section["confidence"] = "job-and-workflow-bound" if jobs.get("status") == "complete" else "job-evidence-partial"
    ci_section["summary"] = "CI/CD maturity combines workflow configuration, run conclusions, job-level outcomes and durations, and bounded deployment-state evidence."

    evidence = ci_section.setdefault("evidence", [])
    _append_unique(
        evidence,
        f"Job-level CI evidence inspected {runs_with_jobs} run(s) and {observed} job(s): success={successful_jobs}, non-success={non_success_jobs}, terminal success rate={success_rate if success_rate is not None else 'unavailable'}.",
    )
    _append_unique(
        evidence,
        f"Median observed job duration: {median_duration if median_duration is not None else 'unavailable'} seconds; job logs were not collected.",
    )
    _append_unique(
        evidence,
        f"Operational workflow controls observed: {', '.join(operational_controls) or 'none'}.",
    )
    _append_unique(
        evidence,
        f"GitHub deployment evidence: observed={deployments_observed}, success={successful_deployments}, non-success={non_success_deployments}.",
    )
    ci_section["verified_claims"] = list(evidence)

    findings = ci_section.setdefault("findings", [])
    failed_samples = _list(jobs.get("failed_job_samples"))
    if non_success_jobs:
        sample_names = [str(item.get("job_name") or "unnamed job") for item in failed_samples if isinstance(item, dict)][:5]
        _append_unique(
            findings,
            f"Review {non_success_jobs} non-success job(s){': ' + ', '.join(sample_names) if sample_names else ''}.",
        )

    unavailable = ci_section.setdefault("unavailable", [])
    unavailable = [
        note
        for note in unavailable
        if str(note) != "Workflow configuration and run conclusions do not replace inspection of failing job logs or deployment-provider evidence."
    ]
    _append_unique(unavailable, "Job logs were not collected; non-success job root causes still require human inspection.")
    if deployments.get("status") in {"unavailable", "partial"}:
        _append_unique(unavailable, "Deployment evidence is incomplete or access-limited for this assessment run.")
    ci_section["unavailable"] = unavailable
    ci_section["unverified_claims"] = list(unavailable)
    ci_section["score_evidence_breakdown"] = {
        "baseline_score": baseline,
        "job_evidence_increment": increment,
        "final_score": score,
        "reasons": reasons,
        "weights_changed": False,
        "thresholds_changed": False,
    }

    assessment.setdefault("scorecard", {})["ci_runtime_evidence"] = {
        "status": workflows.get("runtime_evidence_status") or jobs.get("status") or "unknown",
        "jobs_observed": observed,
        "runs_with_jobs": runs_with_jobs,
        "job_success_rate": success_rate,
        "deployments_observed": deployments_observed,
        "operational_controls": operational_controls,
        "baseline_score": baseline,
        "final_score": score,
        "weights_changed": False,
    }
    _recompute_technical_score(assessment)
    return assessment


def full_assessment_scoring_with_ci_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    result = full_assessment_scoring_handler(context, outputs)
    if result.get("status") != "complete" or not isinstance(result.get("assessment"), dict):
        return result
    repo_output = _dict(outputs.get("repo_evidence"))
    repository_evidence = _dict(repo_output.get("repository_evidence"))
    result["assessment"] = apply_ci_runtime_score(result["assessment"], repository_evidence)
    scorecard = _dict(result["assessment"].get("scorecard"))
    result.setdefault("evidence", {})["technical_score"] = scorecard.get("technical_score", 0)
    result["evidence"]["ci_job_evidence_applied"] = bool(scorecard.get("ci_job_evidence_applied"))
    return result
