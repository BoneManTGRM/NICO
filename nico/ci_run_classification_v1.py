from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico import comprehensive_decision_grade_assessment_v5 as assessment_module
from nico import comprehensive_native_providers as providers
from nico import snapshot_repository_evidence as snapshot_evidence

VERSION = "nico.ci_run_classification.v1"
_MARKER = "_nico_ci_run_classification_v1"

_TERMINAL_CONCLUSIONS = {
    "success",
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "neutral",
    "skipped",
    "stale",
    "startup_failure",
}

_INFRASTRUCTURE_TERMS = (
    "set up job",
    "setup job",
    "runner",
    "checkout",
    "download action",
    "network",
    "rate limit",
    "hosted scanner binaries",
    "provision",
    "container startup",
)

_CODE_TERMS = (
    "test",
    "pytest",
    "lint",
    "eslint",
    "typecheck",
    "typescript",
    "compile",
    "build",
    "codeql",
    "security scan",
    "audit evidence",
    "acceptance",
)

_EXPECTED_CANCEL_TERMS = (
    "concurrency",
    "superseded",
    "newer run",
    "replaced by",
    "duplicate run",
)


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: max(0, limit - 3)].rstrip() + "..."


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _run_text(run: dict[str, Any]) -> str:
    pieces = [
        run.get("name"),
        run.get("display_title"),
        run.get("failure_stage"),
        run.get("failed_step"),
        run.get("job_name"),
        run.get("reason"),
        run.get("cancelled_reason"),
        run.get("status_reason"),
    ]
    jobs = _records(run.get("jobs"))
    for job in jobs:
        pieces.extend((job.get("name"), job.get("failed_step"), job.get("conclusion")))
    return " ".join(_text(item, 240).casefold() for item in pieces if _text(item, 240))


def _classification(run: dict[str, Any]) -> tuple[str, str, str, bool]:
    conclusion = _text(run.get("conclusion"), 60).casefold()
    status = _text(run.get("status"), 60).casefold()
    evidence = _run_text(run)

    if conclusion == "success":
        return "success", "high", "GitHub conclusion=success", False
    if conclusion in {"neutral", "skipped", "stale"}:
        return "informational_non_success", "high", f"GitHub conclusion={conclusion}", False
    if conclusion == "cancelled":
        if any(term in evidence for term in _EXPECTED_CANCEL_TERMS):
            return "expected_cancellation", "high", "Cancellation metadata identifies concurrency or supersession", False
        return "unclassified_cancellation", "low", "GitHub conclusion=cancelled without a retained cause", True
    if conclusion == "timed_out":
        return "timeout", "high", "GitHub conclusion=timed_out", False
    if conclusion == "action_required":
        return "action_required", "high", "GitHub conclusion=action_required", False
    if conclusion == "startup_failure":
        return "infrastructure_failure", "high", "GitHub conclusion=startup_failure", False
    if conclusion == "failure":
        if any(term in evidence for term in _INFRASTRUCTURE_TERMS):
            return "infrastructure_failure", "medium", "Retained failed-stage metadata matches an infrastructure boundary", False
        if any(term in evidence for term in _CODE_TERMS):
            return "code_or_test_failure", "medium", "Retained workflow/job metadata matches a code, test, build, or acceptance boundary", False
        return "unclassified_failure", "low", "GitHub conclusion=failure without sufficient retained cause evidence", True
    if status in {"queued", "in_progress", "pending", "waiting", "requested"} and not conclusion:
        return "non_terminal", "high", f"Run status={status or 'unknown'} has no terminal conclusion", False
    return "unclassified_terminal" if conclusion else "unknown", "low", "Run metadata did not support a bounded classification", bool(conclusion)


def classify_ci_runs(runs: list[dict[str, Any]], *, snapshot_sha: str = "") -> dict[str, Any]:
    ledger: list[dict[str, Any]] = []
    for index, run in enumerate(runs[:200], start=1):
        if not isinstance(run, dict):
            continue
        classification, confidence, basis, requires_review = _classification(run)
        conclusion = _text(run.get("conclusion"), 60).casefold()
        head_sha = _text(run.get("head_sha"), 80)
        ledger.append(
            {
                "run_id": _text(run.get("id") or run.get("run_id"), 120) or f"bounded-run-{index}",
                "workflow_name": _text(run.get("name") or run.get("workflow_name"), 220) or "Unnamed workflow",
                "event": _text(run.get("event"), 80) or "unknown",
                "status": _text(run.get("status"), 60) or "unknown",
                "conclusion": conclusion or "not_terminal",
                "head_sha": head_sha,
                "matches_snapshot_sha": bool(snapshot_sha and head_sha.casefold() == snapshot_sha.casefold()),
                "classification": classification,
                "classification_confidence": confidence,
                "classification_basis": basis,
                "requires_human_cause_review": requires_review,
                "created_at": _text(run.get("created_at"), 80),
                "updated_at": _text(run.get("updated_at"), 80),
                "html_url": _text(run.get("html_url"), 400),
            }
        )

    terminal = [item for item in ledger if item["conclusion"] in _TERMINAL_CONCLUSIONS]
    successes = [item for item in terminal if item["classification"] == "success"]
    expected = [item for item in terminal if item["classification"] in {"expected_cancellation", "informational_non_success"}]
    actionable = [
        item
        for item in terminal
        if item["classification"] in {"code_or_test_failure", "infrastructure_failure", "timeout", "action_required"}
    ]
    unclassified = [item for item in terminal if item["requires_human_cause_review"]]
    denominator = len(successes) + len(actionable) + len(unclassified)
    success_rate = round(len(successes) / denominator, 4) if denominator else None
    exact_sha = [item for item in terminal if item["matches_snapshot_sha"]]
    exact_denominator = sum(
        item["classification"] not in {"expected_cancellation", "informational_non_success"}
        for item in exact_sha
    )
    exact_successes = sum(item["classification"] == "success" for item in exact_sha)
    exact_success_rate = round(exact_successes / exact_denominator, 4) if exact_denominator else None
    status = "complete" if terminal and not unclassified else "review_limited" if terminal else "unavailable"
    return {
        "artifact_schema": VERSION,
        "status": status,
        "runs_received": len(runs),
        "runs_classified": len(ledger),
        "terminal_runs": len(terminal),
        "successful_runs": len(successes),
        "expected_or_informational_non_success_runs": len(expected),
        "actionable_non_success_runs": len(actionable),
        "unclassified_non_success_runs": len(unclassified),
        "release_reliability_denominator": denominator,
        "classified_release_success_rate": success_rate,
        "snapshot_sha": snapshot_sha,
        "exact_sha_terminal_runs": len(exact_sha),
        "exact_sha_release_success_rate": exact_success_rate,
        "classification_complete": bool(terminal) and not unclassified,
        "raw_non_success_runs": sum(item["classification"] != "success" for item in terminal),
        "ledger": ledger,
        "guardrail": "Expected cancellations and informational outcomes are excluded from the classified release-reliability denominator. Unknown causes remain review-limited and are never silently treated as code defects or successful runs.",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _score_band(score: int) -> tuple[str, str, str]:
    if score >= 90:
        return "exceptional", "EXCEPTIONAL", "green"
    if score >= 80:
        return "strong", "STRONG", "green"
    if score >= 70:
        return "moderate", "MODERATE", "yellow"
    if score >= 55:
        return "weak", "WEAK", "red"
    return "critical", "CRITICAL", "red"


def reconcile_assessment_ci_classification(
    assessment: dict[str, Any],
    workflow_evidence: dict[str, Any],
) -> dict[str, Any]:
    output = deepcopy(assessment)
    classification = _record(workflow_evidence.get("ci_run_classification"))
    if not classification:
        return output

    actionable = int(classification.get("actionable_non_success_runs") or 0)
    unclassified = int(classification.get("unclassified_non_success_runs") or 0)
    expected = int(classification.get("expected_or_informational_non_success_runs") or 0)
    successes = int(classification.get("successful_runs") or 0)
    score = 94
    score -= min(30, actionable * 10)
    score -= min(20, unclassified * 4)
    if successes == 0:
        score -= 12
    if not workflow_evidence.get("explicit_permissions_present"):
        score -= 7
    score = max(0, min(100, score))
    band, label, tone = _score_band(score)
    assurance_verified = classification.get("classification_complete") is True and classification.get("status") == "complete"

    sections = _records(output.get("sections"))
    for section in sections:
        if section.get("id") != "ci_cd":
            continue
        section["score_value"] = score
        section["presented_score"] = score
        section["score_band"] = band
        section["score_band_label"] = label
        section["score_tone"] = tone
        section["assurance_status"] = "verified" if assurance_verified else "review_limited"
        section["assurance_label"] = "VERIFIED" if assurance_verified else "REVIEW LIMITED"
        section["assurance_tone"] = "green" if assurance_verified else "yellow"
        section["evidence"] = [
            f"Classified terminal workflow runs: {classification.get('terminal_runs') or 0}.",
            f"Successful runs: {successes}.",
            f"Actionable non-success runs: {actionable}.",
            f"Expected or informational non-success runs excluded from reliability denominator: {expected}.",
            f"Unclassified non-success runs requiring cause review: {unclassified}.",
            f"Classified release success rate: {classification.get('classified_release_success_rate') if classification.get('classified_release_success_rate') is not None else 'not available'}.",
            f"Exact-SHA release success rate: {classification.get('exact_sha_release_success_rate') if classification.get('exact_sha_release_success_rate') is not None else 'not available'}.",
        ]
        findings: list[str] = []
        if actionable:
            findings.append(f"{actionable} actionable CI run outcome(s) require remediation by retained cause class.")
        if unclassified:
            findings.append(f"{unclassified} non-success CI run(s) remain unclassified and prevent verified release-reliability assurance.")
        if not workflow_evidence.get("explicit_permissions_present"):
            findings.append("Workflow configuration did not prove explicit permissions blocks.")
        section["findings"] = findings
        section["unavailable"] = [] if assurance_verified else [
            "CI reliability remains review-limited until every retained non-success run has a cause classification."
        ]
        section["ci_run_classification"] = classification
        section["verified_green_exit_criteria"] = (
            "Every retained non-success run has a reviewed cause classification; recurrent actionable failure classes are repaired; "
            "the approved rolling reliability window meets the project threshold; and the exact-SHA acceptance workflows pass twice."
        )
        break
    output["sections"] = sections

    register = [
        item
        for item in _records(output.get("findings_register"))
        if item.get("id") != "ci-historical-non-success"
    ]
    if actionable:
        register.append(
            {
                "id": "ci-actionable-non-success",
                "priority": "P1",
                "category": "ci_cd",
                "title": f"{actionable} classified actionable CI run outcome(s)",
                "impact": "Repeated code, test, infrastructure, timeout, or approval failures can reduce release reliability and delay delivery.",
                "confidence": "high",
                "evidence": f"classified_actionable_non_success_runs={actionable}",
                "location": "GitHub Actions classified run ledger",
                "recommendation": "Repair recurrent failure classes and verify the affected workflows twice on the exact accepted SHA.",
                "effort": "M",
                "owner_role": "Platform Engineer",
                "acceptance_criteria": "No unexplained recurrent actionable failure class remains in the approved rolling window.",
            }
        )
    if unclassified:
        register.append(
            {
                "id": "ci-unclassified-non-success",
                "priority": "P1",
                "category": "ci_cd",
                "title": f"{unclassified} CI run outcome(s) require cause classification",
                "impact": "Unknown failure causes prevent trustworthy release-reliability metrics and can hide recurring defects.",
                "confidence": "high",
                "evidence": f"unclassified_non_success_runs={unclassified}",
                "location": "GitHub Actions classified run ledger",
                "recommendation": "Review bounded job and step evidence and assign a stable cause class with reviewer rationale.",
                "effort": "S-M",
                "owner_role": "Platform Engineer",
                "acceptance_criteria": "Every retained non-success run has a cause class, confidence, evidence basis, and reviewer disposition.",
            }
        )
    output["findings_register"] = register
    output["ci_run_classification"] = classification

    scored = [
        int(item.get("presented_score"))
        for item in sections
        if isinstance(item.get("presented_score"), (int, float)) and item.get("exclude_from_maturity") is not True
    ]
    if scored:
        overall = round(sum(scored) / len(scored))
        maturity = _record(output.get("maturity_signal"))
        maturity["score"] = overall
        maturity["source_score"] = overall
        maturity["presented_score"] = overall
        maturity["score_band"], maturity["score_band_label"], _ = _score_band(overall)
        output["maturity_signal"] = maturity
    return output


def scoring_provider_with_ci_classification(context: dict[str, Any]) -> dict[str, Any]:
    result = assessment_module.canonical_scoring_provider(context)
    assessment = _record(result.get("assessment"))
    if not assessment:
        return result
    repo = providers._repo(context)
    workflow = _record(repo.get("workflow_evidence"))
    reconciled = reconcile_assessment_ci_classification(assessment, workflow)
    output = deepcopy(result)
    output["assessment"] = reconciled
    evidence = _record(output.get("evidence"))
    classification = _record(workflow.get("ci_run_classification"))
    evidence.update(
        {
            "ci_run_classification_status": classification.get("status") or "unavailable",
            "ci_actionable_non_success_runs": int(classification.get("actionable_non_success_runs") or 0),
            "ci_unclassified_non_success_runs": int(classification.get("unclassified_non_success_runs") or 0),
            "ci_expected_non_success_runs": int(classification.get("expected_or_informational_non_success_runs") or 0),
        }
    )
    output["evidence"] = evidence
    return output


def install_ci_run_classification_v1() -> dict[str, Any]:
    current: Callable[..., dict[str, Any]] = snapshot_evidence._workflow_summary
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "non_success_runs_classified": True,
            "expected_cancellations_excluded_from_reliability": True,
            "unclassified_runs_remain_review_limited": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def workflow_summary_with_classification(
        workflows: dict[str, str],
        runs: list[dict[str, Any]],
        ci: dict[str, Any],
        snapshot_sha: str,
    ) -> dict[str, Any]:
        summary = current(workflows, runs, ci, snapshot_sha)
        classification = classify_ci_runs(runs, snapshot_sha=snapshot_sha)
        summary["raw_non_success_runs"] = summary.get("non_success_runs") or 0
        summary["actionable_non_success_runs"] = classification["actionable_non_success_runs"]
        summary["unclassified_non_success_runs"] = classification["unclassified_non_success_runs"]
        summary["expected_or_informational_non_success_runs"] = classification["expected_or_informational_non_success_runs"]
        summary["classified_release_success_rate"] = classification["classified_release_success_rate"]
        summary["ci_run_classification"] = classification
        return summary

    setattr(workflow_summary_with_classification, _MARKER, True)
    setattr(workflow_summary_with_classification, "_nico_previous", current)
    snapshot_evidence._workflow_summary = workflow_summary_with_classification
    return {
        "status": "installed",
        "version": VERSION,
        "non_success_runs_classified": True,
        "expected_cancellations_excluded_from_reliability": True,
        "unclassified_runs_remain_review_limited": True,
        "same_snapshot_sha_separated": True,
        "raw_logs_retained": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "classify_ci_runs",
    "install_ci_run_classification_v1",
    "reconcile_assessment_ci_classification",
    "scoring_provider_with_ci_classification",
]
