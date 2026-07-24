from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

VERSION = "nico.ci_run_classification.v1"
_NEUTRAL_CONCLUSIONS = {"neutral", "skipped"}
_INFRASTRUCTURE_CONCLUSIONS = {"timed_out", "stale", "startup_failure", "action_required"}


def _timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _identity(run: dict[str, Any]) -> tuple[str, str]:
    workflow = str(run.get("workflow_id") or run.get("name") or run.get("path") or "unknown_workflow")
    branch = str(run.get("head_branch") or "")
    return workflow, branch


def _newer_equivalent_exists(run: dict[str, Any], runs: list[dict[str, Any]]) -> bool:
    created = _timestamp(run.get("created_at") or run.get("run_started_at"))
    workflow, branch = _identity(run)
    head_sha = str(run.get("head_sha") or "")
    run_id = str(run.get("id") or "")
    for candidate in runs:
        if str(candidate.get("id") or "") == run_id:
            continue
        candidate_created = _timestamp(candidate.get("created_at") or candidate.get("run_started_at"))
        if created is not None and candidate_created is not None and candidate_created <= created:
            continue
        candidate_workflow, candidate_branch = _identity(candidate)
        same_workflow = candidate_workflow == workflow
        same_branch = bool(branch) and candidate_branch == branch
        same_sha = bool(head_sha) and str(candidate.get("head_sha") or "") == head_sha
        if same_workflow and (same_branch or same_sha):
            return True
    return False


def classify_workflow_run(run: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    conclusion = str(run.get("conclusion") or "").strip().lower()
    status = str(run.get("status") or "").strip().lower()
    category = "unclassified"
    release_relevant = False
    counts_as_failure = False
    explanation = "The available workflow-run metadata does not establish a safe cause classification."

    if conclusion == "success":
        category = "success"
        release_relevant = True
        explanation = "GitHub reported a successful workflow conclusion."
    elif conclusion in _NEUTRAL_CONCLUSIONS:
        category = "neutral_or_skipped"
        explanation = f"GitHub reported the non-failure conclusion {conclusion}."
    elif conclusion == "cancelled":
        if _newer_equivalent_exists(run, runs):
            category = "superseded_or_cancelled"
            explanation = "A newer run exists for the same workflow and branch or commit, so this cancellation is excluded from release-failure scoring."
        else:
            category = "cancelled_unclassified"
            release_relevant = True
            explanation = "The run was cancelled, but the available metadata does not prove that it was superseded or intentionally stopped."
    elif conclusion in _INFRASTRUCTURE_CONCLUSIONS:
        category = "infrastructure_or_platform"
        release_relevant = True
        counts_as_failure = True
        explanation = f"GitHub reported {conclusion}, which is tracked separately from a confirmed code or test regression."
    elif conclusion == "failure":
        category = "failure_unclassified"
        release_relevant = True
        explanation = "GitHub reported failure, but run-level metadata alone cannot distinguish code, test, workflow, dependency, or platform cause."
    elif conclusion:
        category = "unclassified_conclusion"
        release_relevant = True
        explanation = f"GitHub reported conclusion {conclusion}, which is not mapped to a confirmed engineering cause."
    elif status in {"queued", "in_progress", "waiting", "requested", "pending"}:
        category = "active_not_final"
        explanation = "The workflow has not reached a final conclusion and is excluded from historical reliability scoring."

    return {
        "run_id": str(run.get("id") or ""),
        "name": str(run.get("name") or run.get("path") or "unknown workflow"),
        "event": str(run.get("event") or "unknown"),
        "head_branch": str(run.get("head_branch") or ""),
        "head_sha": str(run.get("head_sha") or ""),
        "status": status,
        "conclusion": conclusion or "unavailable",
        "category": category,
        "release_relevant": release_relevant,
        "counts_as_failure": counts_as_failure,
        "cause_verified": category in {"success", "neutral_or_skipped", "superseded_or_cancelled", "infrastructure_or_platform"},
        "explanation": explanation,
    }


def classify_workflow_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_runs = [run for run in runs if isinstance(run, dict)]
    classifications = [classify_workflow_run(run, normalized_runs) for run in normalized_runs]
    counts = Counter(item["category"] for item in classifications)
    release_relevant = [item for item in classifications if item["release_relevant"]]
    successes = sum(1 for item in release_relevant if item["category"] == "success")
    confirmed_failures = sum(1 for item in release_relevant if item["counts_as_failure"])
    unresolved = [
        item
        for item in release_relevant
        if item["category"] in {"failure_unclassified", "cancelled_unclassified", "unclassified_conclusion", "unclassified"}
    ]
    denominator = successes + confirmed_failures
    reliability = successes / denominator if denominator else None
    return {
        "artifact_schema": VERSION,
        "runs_observed": len(classifications),
        "category_counts": dict(sorted(counts.items())),
        "release_relevant_runs": len(release_relevant),
        "success_count": successes,
        "confirmed_failure_count": confirmed_failures,
        "unclassified_non_success_count": len(unresolved),
        "classified_reliability_rate": reliability,
        "reliability_decision_grade": reliability is not None and not unresolved,
        "classifications": classifications,
        "unresolved_runs": unresolved,
        "truth_rule": "Cancelled runs are not treated as code failures without supersession evidence; failure conclusions remain unclassified until cause evidence exists.",
    }


def analyze_ci_classified(
    workflows: dict[str, str],
    workflow_unavailable: list[str],
    workflow_runs: list[dict[str, Any]],
    runs_error: str | None,
) -> dict[str, Any]:
    evidence: list[str] = []
    findings: list[str] = []
    unavailable = list(workflow_unavailable)
    score = 20
    combined = "\n".join(workflows.values()).lower()

    if workflows:
        evidence.append(f"GitHub Actions workflows found: {', '.join(workflows.keys())}.")
        score = 55
        if any(term in combined for term in ["pytest", "npm run lint", "next build", "npm test", "ruff", "mypy", "eslint"]):
            score += 18
            evidence.append("Workflow text includes test, lint, or build commands.")
        else:
            findings.append("Workflow files exist but no obvious test/lint/build command was detected.")
        if "permissions:" in combined:
            score += 7
            evidence.append("Workflow text includes explicit permissions blocks.")
        else:
            findings.append("Workflow files do not show explicit permissions blocks in inspected text.")
        if any(term in combined for term in ["deploy", "vercel", "render", "railway", "flyctl", "docker"]):
            score += 8
            evidence.append("Workflow text includes deployment-related commands or providers.")
        if "secrets." in combined:
            evidence.append("Workflow text references GitHub secrets, which is expected for controlled deploy credentials but should be reviewed.")
    else:
        evidence.append("No GitHub Actions workflow files were available for analysis.")
        findings.append("No CI/CD workflow files were found through GitHub contents access.")

    classification: dict[str, Any] = {
        "artifact_schema": VERSION,
        "runs_observed": 0,
        "category_counts": {},
        "unclassified_non_success_count": 0,
        "reliability_decision_grade": False,
        "classifications": [],
        "unresolved_runs": [],
    }
    if runs_error:
        unavailable.append(f"Workflow run history unavailable: {runs_error}")
    else:
        recent = [run for run in workflow_runs[:100] if isinstance(run, dict)]
        classification = classify_workflow_runs(recent)
        counts = classification["category_counts"]
        evidence.append(
            "GitHub Actions workflow runs returned in assessment window: "
            f"{classification['runs_observed']}; categories={counts}."
        )
        if classification["reliability_decision_grade"]:
            rate = classification["classified_reliability_rate"]
            evidence.append(f"Cause-classified release reliability: {rate:.1%}.")
            if rate >= 0.8:
                score += 8
            elif classification["confirmed_failure_count"]:
                findings.append("Cause-classified workflow history shows confirmed non-success reliability pressure.")
                score -= 8
        elif classification["unclassified_non_success_count"]:
            findings.append(
                f"{classification['unclassified_non_success_count']} non-success workflow run(s) remain cause-unclassified; "
                "release reliability is review-limited until each run is dispositioned."
            )
            unavailable.append(
                "CI reliability was not promoted from raw workflow conclusions because one or more non-success runs lack cause evidence."
            )
        elif recent:
            unavailable.append("No final release-relevant workflow conclusions were available for a decision-grade reliability rate.")

    return {
        "score": max(20, min(score, 95)),
        "summary": "CI/CD maturity is based on workflow configuration and cause-classified run history. Raw cancellations and failures are not automatically treated as code regressions.",
        "evidence": evidence + findings,
        "findings": findings,
        "unavailable": unavailable,
        "ci_run_classification": classification,
    }


def install_ci_run_classification() -> dict[str, Any]:
    from nico import hosted_assessment

    current = hosted_assessment.analyze_ci
    if getattr(current, "_nico_ci_run_classification_v1", False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "cancelled_runs_auto_failed": False,
            "unclassified_failures_disclosed": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    setattr(analyze_ci_classified, "_nico_ci_run_classification_v1", True)
    setattr(analyze_ci_classified, "_nico_previous", current)
    hosted_assessment.analyze_ci = analyze_ci_classified
    return {
        "status": "installed",
        "version": VERSION,
        "cancelled_runs_auto_failed": False,
        "unclassified_failures_disclosed": True,
        "cause_classification_required_for_decision_grade_reliability": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "analyze_ci_classified",
    "classify_workflow_run",
    "classify_workflow_runs",
    "install_ci_run_classification",
]
