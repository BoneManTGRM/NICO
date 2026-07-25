from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Iterable, Literal

VERSION = "nico.decision_grade_ci_reliability.v1"
_MARKER = "__nico_decision_grade_ci_reliability_v1__"

RunClass = Literal[
    "success",
    "code_or_test_failure",
    "infrastructure_failure",
    "timeout",
    "cancelled_expected",
    "cancelled_unclassified",
    "skipped_or_neutral",
    "unknown_non_success",
]

_FAILURE_WORDS = {
    "test": ("pytest", "jest", "vitest", "test", "assert", "coverage"),
    "code": ("compile", "typecheck", "lint", "build", "syntax", "mypy", "tsc"),
    "infra": (
        "runner lost", "hosted runner", "service unavailable", "connection reset",
        "network", "dns", "rate limit", "artifact upload", "docker pull",
        "registry", "out of disk", "no space left", "database unavailable",
        "postgres connection",
    ),
    "timeout": ("timed out", "timeout", "deadline exceeded"),
}


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _normalized(value: Any) -> str:
    return _text(value, 500).casefold().replace("-", "_").replace(" ", "_")


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _contains_any(text: str, values: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(value in lowered for value in values)


def classify_ci_run(run: dict[str, Any]) -> dict[str, Any]:
    conclusion = _normalized(run.get("conclusion") or run.get("status"))
    event = _normalized(run.get("event"))
    name = _text(run.get("name") or run.get("workflow_name") or run.get("display_title"), 300)
    details = " ".join(
        _text(run.get(key), 1200)
        for key in ("failure_reason", "message", "summary", "logs_excerpt", "job_name", "failed_step")
    )
    combined = f"{name} {details}".strip()
    expected_cancel = bool(
        run.get("expected_cancellation") is True
        or run.get("superseded") is True
        or run.get("concurrency_cancelled") is True
        or run.get("cancel_reason") in {"superseded", "newer_run", "concurrency"}
    )

    classification: RunClass
    included = False
    failed = False
    rationale = ""

    if conclusion in {"success", "completed_success", "passed", "green"}:
        classification = "success"
        included = True
        rationale = "Workflow completed successfully."
    elif conclusion in {"skipped", "neutral", "not_applicable", "action_required"}:
        classification = "skipped_or_neutral"
        rationale = "Run did not produce an equivalent reliability result."
    elif conclusion in {"cancelled", "canceled"}:
        if expected_cancel:
            classification = "cancelled_expected"
            rationale = "Cancellation was explicitly classified as superseded or expected concurrency behavior."
        else:
            classification = "cancelled_unclassified"
            rationale = "Cancellation lacks evidence proving whether it was expected or failure-related."
    elif conclusion in {"timed_out", "timeout"} or _contains_any(combined, _FAILURE_WORDS["timeout"]):
        classification = "timeout"
        included = True
        failed = True
        rationale = "The run exceeded an execution deadline."
    elif conclusion in {"failure", "failed", "error", "startup_failure", "stale"}:
        if _contains_any(combined, _FAILURE_WORDS["infra"]):
            classification = "infrastructure_failure"
            included = True
            failed = True
            rationale = "Failure evidence points to runner, network, registry, storage, or service infrastructure."
        elif _contains_any(combined, (*_FAILURE_WORDS["test"], *_FAILURE_WORDS["code"])):
            classification = "code_or_test_failure"
            included = True
            failed = True
            rationale = "Failure evidence points to code, build, static-check, or automated-test execution."
        else:
            classification = "unknown_non_success"
            rationale = "Non-success conclusion lacks enough evidence for code/test versus infrastructure attribution."
    else:
        classification = "unknown_non_success"
        rationale = "Run conclusion is missing or unsupported."

    return {
        "run_id": _text(run.get("run_id") or run.get("id"), 180),
        "workflow_name": name,
        "event": event or "unknown",
        "commit_sha": _text(run.get("commit_sha") or run.get("head_sha"), 80),
        "started_at": _text(run.get("started_at") or run.get("created_at"), 100),
        "completed_at": _text(run.get("completed_at") or run.get("updated_at"), 100),
        "raw_conclusion": conclusion or "unknown",
        "classification": classification,
        "reliability_denominator_included": included,
        "failure_numerator_included": failed,
        "expected_cancellation": expected_cancel,
        "rationale": rationale,
        "evidence_reference": _text(run.get("html_url") or run.get("url") or run.get("evidence_reference"), 600),
    }


def build_ci_reliability_evidence(
    runs: list[dict[str, Any]] | None,
    *,
    requested_workflows: list[str] | None = None,
    coverage_window_days: int = 90,
) -> dict[str, Any]:
    classified = [classify_ci_run(item) for item in _records(runs)]
    denominator = [item for item in classified if item["reliability_denominator_included"]]
    failures = [item for item in denominator if item["failure_numerator_included"]]
    successes = [item for item in denominator if item["classification"] == "success"]
    unknown = [item for item in classified if item["classification"] in {"unknown_non_success", "cancelled_unclassified"}]
    requested = sorted({_text(item, 300) for item in requested_workflows or [] if _text(item, 300)})
    observed = sorted({str(item["workflow_name"]) for item in classified if item["workflow_name"]})
    missing = sorted(set(requested) - set(observed))
    success_rate = round((len(successes) / len(denominator)) * 100, 2) if denominator else None
    failure_rate = round((len(failures) / len(denominator)) * 100, 2) if denominator else None
    classes = (
        "success", "code_or_test_failure", "infrastructure_failure", "timeout",
        "cancelled_expected", "cancelled_unclassified", "skipped_or_neutral", "unknown_non_success",
    )
    complete = bool(classified) and not unknown and not missing
    return {
        "artifact_schema": VERSION,
        "status": "complete" if complete else "partial",
        "assurance": "VERIFIED" if complete else "REVIEW LIMITED",
        "coverage_window_days": max(1, int(coverage_window_days)),
        "requested_workflows": requested,
        "observed_workflows": observed,
        "missing_requested_workflows": missing,
        "total_runs_observed": len(classified),
        "reliability_denominator": len(denominator),
        "success_count": len(successes),
        "failure_count": len(failures),
        "success_rate_percent": success_rate,
        "failure_rate_percent": failure_rate,
        "classification_counts": {key: sum(item["classification"] == key for item in classified) for key in classes},
        "unclassified_non_success_count": len(unknown),
        "classified_runs": classified,
        "guardrail": (
            "Expected cancellations, skipped or neutral runs, and unclassified non-success outcomes are not silently counted as code failures. "
            "Reliability percentages use only success, classified code/test failure, classified infrastructure failure, and timeout outcomes."
        ),
        "technical_score_change_allowed": False,
        "human_review_required": bool(unknown or missing),
        "client_delivery_allowed": False,
    }


def _candidate_runs(stage_results: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], int]:
    for stage in (
        stage_results.get("ci_cd_reliability"),
        stage_results.get("repository_and_delivery_evidence"),
        stage_results.get("historical_trends_and_change_failure"),
    ):
        if not isinstance(stage, dict):
            continue
        runs = stage.get("workflow_runs") or stage.get("ci_runs") or stage.get("runs")
        if isinstance(runs, list):
            requested = stage.get("requested_workflows") if isinstance(stage.get("requested_workflows"), list) else []
            window = stage.get("coverage_window_days") or stage.get("timeframe_days") or 90
            return _records(runs), [str(item) for item in requested], int(window)
    return [], [], 90


def wrap_report_builder_with_ci_reliability(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        stages = kwargs.get("stage_results") if isinstance(kwargs.get("stage_results"), dict) else {}
        runs, requested, window = _candidate_runs(stages)
        evidence = build_ci_reliability_evidence(runs, requested_workflows=requested, coverage_window_days=window)
        result["ci_reliability_evidence"] = evidence
        package = result.get("report_package")
        if isinstance(package, dict):
            package["ci_reliability_evidence"] = evidence
            canonical = package.get("json")
            if isinstance(canonical, dict):
                canonical["ci_reliability_evidence"] = evidence
            quality = package.get("quality") if isinstance(package.get("quality"), dict) else {}
            quality.update({
                "decision_grade_ci_reliability_version": VERSION,
                "ci_run_classification_present": True,
                "ci_unclassified_non_success_count": evidence["unclassified_non_success_count"],
                "ci_expected_cancellations_excluded": True,
                "ci_reliability_denominator": evidence["reliability_denominator"],
                "ci_reliability_client_delivery_allowed": False,
            })
            package["quality"] = quality
        return result

    setattr(wrapped, _MARKER, True)
    return wrapped


__all__ = ["VERSION", "build_ci_reliability_evidence", "classify_ci_run", "wrap_report_builder_with_ci_reliability"]
