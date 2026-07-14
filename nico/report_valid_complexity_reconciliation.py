from __future__ import annotations

from typing import Any


BOUNDED_API_SOURCE = "github_api_exact_commit_bounded_sample"
STALE_INVALID_COMPLEXITY_FRAGMENTS = (
    "complexity evidence unavailable for scoring:",
    "maintainability and complexity conclusions remain unavailable until a valid same-run analyzer artifact is attached",
    "complexity-dependent architecture and technical-debt conclusions are not verified for this report run",
    "the same-run analyzer did not produce valid measurements",
    "invalid_or_zero_complexity_evidence",
)
BOUNDED_SCOPE_LIMITATION = (
    "Bounded GitHub API complexity evidence does not include whole-repository churn, ownership concentration, "
    "or complete call-graph coverage."
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in _list(result.get("sections")):
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _remove_stale_invalid_lines(section: dict[str, Any]) -> None:
    lowered = tuple(fragment.lower() for fragment in STALE_INVALID_COMPLEXITY_FRAGMENTS)
    for key in ("evidence", "findings", "unavailable", "verified_claims", "unverified_claims"):
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [
            item
            for item in values
            if not any(fragment in str(item).lower() for fragment in lowered)
        ]


def _profile(result: dict[str, Any]) -> dict[str, Any]:
    artifact = _dict(result.get("complexity_artifact"))
    value = _dict(artifact.get("profile"))
    if value:
        return value
    value = _dict(result.get("complexity_engine"))
    if value:
        return value
    scanner = _dict(result.get("scanner_worker_artifact"))
    return _dict(scanner.get("complexity_engine"))


def _source(result: dict[str, Any], profile: dict[str, Any]) -> str:
    artifact = _dict(result.get("complexity_artifact"))
    return str(
        artifact.get("source")
        or profile.get("source")
        or "checked_out_repository_complexity"
    )


def _scope(result: dict[str, Any], profile: dict[str, Any], source: str) -> str:
    artifact = _dict(result.get("complexity_artifact"))
    explicit = artifact.get("evidence_scope") or profile.get("evidence_scope")
    if explicit:
        return str(explicit)
    if source == BOUNDED_API_SOURCE:
        return "Bounded exact-commit production-source sample fetched through the authorized GitHub API."
    return "Same-run checked-out repository complexity profile."


def _metrics(result: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    artifact = _dict(result.get("complexity_artifact"))
    summary = _dict(artifact.get("summary"))
    guard = _dict(_dict(result.get("report_quality_guards")).get("cross_tier_complexity_consistency"))
    return {
        "analyzed_files": _int(
            guard.get("analyzed_file_count")
            or profile.get("analyzed_file_count")
            or profile.get("files_analyzed")
            or summary.get("analyzed_file_count")
        ),
        "source_loc": _int(
            guard.get("total_loc")
            or profile.get("total_loc")
            or profile.get("total_source_loc")
            or summary.get("total_loc")
        ),
        "function_units": _int(
            guard.get("total_functions")
            or profile.get("total_functions")
            or profile.get("functions_measured")
            or summary.get("total_functions")
        ),
        "risk": str(
            guard.get("risk_level")
            or profile.get("risk_level")
            or profile.get("risk")
            or summary.get("risk_level")
            or "unknown"
        ).strip().lower(),
    }


def _reconcile_score_lift_metadata(section: dict[str, Any]) -> None:
    score_lift = section.get("scanner_score_lift")
    if not isinstance(score_lift, dict):
        return
    if score_lift.get("blocked_reason") == "invalid_or_zero_complexity_evidence":
        score_lift.pop("blocked_reason", None)
    score_lift["complexity_evidence_reconciled"] = True


def _refresh_claim_lists(section: dict[str, Any]) -> None:
    section["verified_claims"] = list(_list(section.get("evidence")))
    section["unverified_claims"] = list(_list(section.get("unavailable")))


def reconcile_verified_complexity_report_state(result: dict[str, Any]) -> dict[str, Any]:
    """Remove obsolete invalid-analyzer wording after valid same-run proof arrives.

    The reconciliation changes report wording and claim lists only. It does not
    raise or cap scores, change section colors, alter maturity, remove distinct
    limitations, approve the report, or change client-delivery state.
    """

    if result.get("status") != "complete":
        return result
    guards = result.setdefault("report_quality_guards", {})
    consistency = _dict(guards.get("cross_tier_complexity_consistency"))
    if consistency.get("verified_for_scoring") is not True or consistency.get("status") != "verified":
        return result

    profile = _profile(result)
    metrics = _metrics(result, profile)
    if not profile or min(metrics["analyzed_files"], metrics["source_loc"], metrics["function_units"]) <= 0:
        return result

    source = _source(result, profile)
    evidence_scope = _scope(result, profile, source)
    bounded = source == BOUNDED_API_SOURCE
    detail = (
        "Complexity evidence verified for this report run: "
        f"analyzed_files={metrics['analyzed_files']}, LOC={metrics['source_loc']}, "
        f"function_units={metrics['function_units']}, risk={metrics['risk']}, source={source}."
    )

    velocity = _section(result, "velocity_complexity")
    if velocity:
        score = velocity.get("score")
        status = velocity.get("status")
        _remove_stale_invalid_lines(velocity)
        velocity.setdefault("evidence", [])
        velocity.setdefault("unavailable", [])
        _append_unique(velocity["evidence"], detail)
        if bounded:
            velocity["summary"] = (
                "Commit and pull-request activity plus a valid exact-commit bounded complexity sample are available. "
                "The measured sample is score-eligible; full-checkout churn, ownership concentration, and complete "
                "call-graph coverage remain outside this evidence scope."
            )
            _append_unique(velocity["unavailable"], BOUNDED_SCOPE_LIMITATION)
        else:
            velocity["summary"] = (
                "Velocity and complexity review includes valid same-run checked-out repository measurements with "
                "positive analyzed-file, source-LOC, and function-unit evidence."
            )
        velocity["score"] = score
        velocity["status"] = status
        _reconcile_score_lift_metadata(velocity)
        _refresh_claim_lists(velocity)

    architecture = _section(result, "architecture_debt")
    if architecture:
        score = architecture.get("score")
        status = architecture.get("status")
        _remove_stale_invalid_lines(architecture)
        architecture.setdefault("evidence", [])
        architecture.setdefault("unavailable", [])
        _append_unique(architecture["evidence"], detail)
        if bounded:
            architecture["summary"] = (
                "Architecture review includes valid exact-commit bounded complexity measurements. Full-checkout "
                "history-backed churn, ownership, and complete call-graph signals remain outside this evidence scope."
            )
            _append_unique(architecture["unavailable"], BOUNDED_SCOPE_LIMITATION)
        else:
            architecture["summary"] = (
                "Architecture review includes valid same-run checked-out repository complexity measurements with "
                "positive source, LOC, and function-unit evidence."
            )
        architecture["score"] = score
        architecture["status"] = status
        _refresh_claim_lists(architecture)

    guards["verified_complexity_reconciliation"] = {
        "status": "reconciled",
        "source": source,
        "evidence_scope": evidence_scope,
        "bounded_sample": bounded,
        "analyzed_file_count": metrics["analyzed_files"],
        "total_loc": metrics["source_loc"],
        "total_functions": metrics["function_units"],
        "risk_level": metrics["risk"],
        "score_changed": False,
        "status_changed": False,
        "human_review_changed": False,
        "guardrail": "Obsolete invalid-analyzer wording is removed only after the same consistency gate verifies positive same-run measurements.",
    }
    return result


__all__ = [
    "BOUNDED_API_SOURCE",
    "BOUNDED_SCOPE_LIMITATION",
    "reconcile_verified_complexity_report_state",
]
