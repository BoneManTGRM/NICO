from __future__ import annotations

from typing import Any

INVALID_COMPLEXITY_RISKS = {
    "review_required",
    "unavailable",
    "unknown",
    "failed",
    "error",
    "blocked",
    "not_run",
}
COMPLEXITY_LINE_FRAGMENTS = (
    "complexity engine current-run artifact completed",
    "complexity artifact bound to",
    "architecture complexity support",
    "verified score lift: dependency/static proof and complexity evidence",
)
STALE_SECRET_HISTORY_FRAGMENTS = (
    "sampled current-tree review is not full git-history proof",
    "dedicated history scanner remains required",
    "full git-history secret coverage is not verified",
    "live gitleaks/trufflehog history evidence was not attached",
    "full-history secret coverage is unavailable or unverified",
    "history coverage remains a separate limitation",
)
SECRET_TOOLS = ("gitleaks", "trufflehog")
CLEAN_TOOL_STATUSES = {"completed", "completed_clean", "passed"}


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


def _status_from_score(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 55:
        return "yellow"
    return "red"


def _remove_lines(section: dict[str, Any], fragments: tuple[str, ...], keys: tuple[str, ...]) -> None:
    lowered = tuple(fragment.lower() for fragment in fragments)
    for key in keys:
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [
            item
            for item in values
            if not any(fragment in str(item).lower() for fragment in lowered)
        ]


def _scanner_artifact(result: dict[str, Any]) -> dict[str, Any]:
    return _dict(result.get("scanner_worker_artifact"))


def _complexity_artifact(result: dict[str, Any]) -> dict[str, Any]:
    return _dict(result.get("complexity_artifact"))


def _complexity_profile(result: dict[str, Any]) -> dict[str, Any]:
    artifact = _complexity_artifact(result)
    profile = _dict(artifact.get("profile"))
    if profile:
        return profile
    profile = _dict(result.get("complexity_engine"))
    if profile:
        return profile
    profile = _dict(_scanner_artifact(result).get("complexity_engine"))
    if profile:
        return profile
    return _dict(result.get("complexity_engine_summary"))


def _complexity_metrics(result: dict[str, Any]) -> dict[str, Any]:
    profile = _complexity_profile(result)
    artifact = _complexity_artifact(result)
    summary = _dict(artifact.get("summary"))
    analyzed_files = _int(
        profile.get("analyzed_file_count")
        or profile.get("files_analyzed")
        or summary.get("analyzed_file_count")
        or summary.get("source_file_count")
    )
    source_loc = _int(
        profile.get("total_loc")
        or profile.get("total_source_loc")
        or summary.get("total_loc")
        or summary.get("source_loc")
    )
    function_units = _int(
        profile.get("total_functions")
        or profile.get("functions_measured")
        or summary.get("total_functions")
        or summary.get("function_count")
    )
    risk = str(
        profile.get("risk_level")
        or profile.get("risk")
        or summary.get("risk_level")
        or "unknown"
    ).strip().lower()
    return {
        "profile": profile,
        "artifact": artifact,
        "analyzed_files": analyzed_files,
        "source_loc": source_loc,
        "function_units": function_units,
        "risk": risk,
    }


def _complexity_is_verified(result: dict[str, Any], metrics: dict[str, Any]) -> bool:
    artifact = _dict(metrics.get("artifact"))
    if not _dict(metrics.get("profile")):
        return False
    if metrics["analyzed_files"] <= 0 or metrics["source_loc"] <= 0 or metrics["function_units"] <= 0:
        return False
    if metrics["risk"] in INVALID_COMPLEXITY_RISKS:
        return False
    if artifact:
        if artifact.get("verified_for_this_report") is not True:
            return False
        if str(artifact.get("status") or "").lower() not in {"completed", "completed_clean", "attached"}:
            return False
        artifact_run = str(artifact.get("report_run_id") or "")
        result_run = str(result.get("report_run_id") or result.get("run_id") or "")
        if artifact_run and result_run and artifact_run != result_run:
            return False
    return True


def _invalidate_complexity_artifact(result: dict[str, Any], metrics: dict[str, Any]) -> None:
    artifact = _complexity_artifact(result)
    if artifact:
        artifact["status"] = "unavailable"
        artifact["verified_for_this_report"] = False
        artifact["guardrail"] = (
            "Complexity evidence cannot support scoring until the same report run contains positive analyzed-file, LOC, "
            "and function-unit measurements with a non-blocking risk state."
        )
    guards = result.setdefault("report_quality_guards", {})
    complexity_guard = guards.setdefault("complexity_artifact", {})
    complexity_guard.update(
        {
            "status": "unavailable",
            "verified_for_this_report": False,
            "score_lift_allowed": False,
            "analyzed_file_count": metrics["analyzed_files"],
            "total_loc": metrics["source_loc"],
            "total_functions": metrics["function_units"],
            "risk_level": metrics["risk"],
            "guardrail": "A zero-measurement or review-required complexity artifact cannot support a verified score lift.",
        }
    )


def _apply_complexity_gate(result: dict[str, Any]) -> bool:
    metrics = _complexity_metrics(result)
    verified = _complexity_is_verified(result, metrics)
    guards = result.setdefault("report_quality_guards", {})
    guards["cross_tier_complexity_consistency"] = {
        "status": "verified" if verified else "blocked",
        "verified_for_scoring": verified,
        "analyzed_file_count": metrics["analyzed_files"],
        "total_loc": metrics["source_loc"],
        "total_functions": metrics["function_units"],
        "risk_level": metrics["risk"],
        "guardrail": "Express and Mid may differ in depth, but they must use the same evidence-validity rule for complexity scoring.",
    }

    bridge = result.setdefault("final_evidence_score_bridge", {})
    bridge["complexity_profile_attached"] = verified
    bridge["complexity_profile_verified"] = verified

    if verified:
        return False

    _invalidate_complexity_artifact(result, metrics)
    detail = (
        "Complexity evidence unavailable for scoring: "
        f"analyzed_files={metrics['analyzed_files']}, LOC={metrics['source_loc']}, "
        f"function_units={metrics['function_units']}, risk={metrics['risk']}."
    )
    changed = False
    velocity = _section(result, "velocity_complexity")
    if velocity:
        prior = _int(velocity.get("score"))
        _remove_lines(velocity, COMPLEXITY_LINE_FRAGMENTS, ("evidence", "findings", "unavailable"))
        velocity.setdefault("evidence", [])
        velocity.setdefault("unavailable", [])
        _append_unique(velocity["evidence"], detail)
        _append_unique(
            velocity["unavailable"],
            "Maintainability and complexity conclusions remain unavailable until a valid same-run analyzer artifact is attached.",
        )
        velocity["verified_claims"] = list(velocity["evidence"])
        velocity["unverified_claims"] = list(velocity["unavailable"])
        velocity["score"] = min(prior, 79)
        velocity["status"] = _status_from_score(_int(velocity.get("score")))
        velocity["summary"] = (
            "Commit and pull-request activity is available, but maintainability and complexity remain review-limited because "
            "the same-run analyzer did not produce valid measurements."
        )
        velocity.setdefault("scanner_score_lift", {})["applied"] = False
        velocity["scanner_score_lift"]["blocked_reason"] = "invalid_or_zero_complexity_evidence"
        changed = changed or _int(velocity.get("score")) != prior

    architecture = _section(result, "architecture_debt")
    if architecture:
        prior = _int(architecture.get("score"))
        _remove_lines(architecture, COMPLEXITY_LINE_FRAGMENTS, ("evidence", "findings", "unavailable"))
        architecture.setdefault("evidence", [])
        architecture.setdefault("unavailable", [])
        _append_unique(architecture["evidence"], detail)
        _append_unique(
            architecture["unavailable"],
            "Complexity-dependent architecture and technical-debt conclusions are not verified for this report run.",
        )
        architecture["verified_claims"] = list(architecture["evidence"])
        architecture["unverified_claims"] = list(architecture["unavailable"])
        architecture["score"] = min(prior, 89)
        architecture["status"] = _status_from_score(_int(architecture.get("score")))
        changed = changed or _int(architecture.get("score")) != prior

    return changed


def _tools(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bundle = _dict(result.get("scanner_artifacts"))
    tools = _dict(bundle.get("tools"))
    if not tools:
        tools = _dict(_scanner_artifact(result).get("tools"))
    return {str(name).lower(): payload for name, payload in tools.items() if isinstance(payload, dict)}


def _finding_count(tool: dict[str, Any]) -> int:
    if isinstance(tool.get("findings_count"), int):
        return int(tool["findings_count"])
    if isinstance(tool.get("finding_count"), int):
        return int(tool["finding_count"])
    return len(_list(tool.get("findings")))


def _tool_clean(tool: dict[str, Any]) -> bool:
    status = str(tool.get("evidence_status") or tool.get("execution_status") or tool.get("status") or "").lower()
    return status in CLEAN_TOOL_STATUSES and _finding_count(tool) == 0 and tool.get("verified_for_this_report") is not False


def _secret_history_verified(result: dict[str, Any]) -> bool:
    tools = _tools(result)
    if not all(name in tools and _tool_clean(tools[name]) for name in SECRET_TOOLS):
        return False
    artifact = _scanner_artifact(result)
    history = _dict(result.get("secret_history_scan")) or _dict(artifact.get("secret_history_scan"))
    completed = {str(item).lower() for item in _list(history.get("completed_tools"))}
    if all(name in completed for name in SECRET_TOOLS) and (
        history.get("full_history_verified") is True or history.get("history_aware") is True
    ):
        return True
    checkout = _dict(artifact.get("checkout"))
    if (
        all(name in completed for name in SECRET_TOOLS)
        and checkout.get("full_history_secret_scan_requested")
        and str(checkout.get("history_depth") or "").lower() == "full"
    ):
        return True
    return all(tools[name].get("full_history_covered") is True for name in SECRET_TOOLS)


def _reconcile_secret_history(result: dict[str, Any]) -> None:
    verified = _secret_history_verified(result)
    result.setdefault("report_quality_guards", {})["secret_history_consistency"] = {
        "status": "verified" if verified else "review_required",
        "full_history_verified": verified,
        "guardrail": "Current-tree limitations remain disclosed unless both clean history scanners are verified for the same report run.",
    }
    if not verified:
        return
    section = _section(result, "secrets_review")
    if not section:
        return
    _remove_lines(section, STALE_SECRET_HISTORY_FRAGMENTS, ("findings", "unavailable"))
    section.setdefault("evidence", [])
    _append_unique(
        section["evidence"],
        "Secret-history limitation reconciled: current-run Gitleaks and TruffleHog completed clean against verified full repository history.",
    )
    section["verified_claims"] = list(section["evidence"])
    section["unverified_claims"] = list(section.get("unavailable") or [])


def _recompute_maturity(result: dict[str, Any]) -> None:
    sections = [
        item
        for item in _list(result.get("sections"))
        if isinstance(item, dict)
        and item.get("status") != "gray"
        and item.get("supplemental") is not True
        and _int(item.get("scoring_weight", 1)) != 0
    ]
    if not sections:
        return
    score = round(sum(_int(item.get("score")) for item in sections) / len(sections))
    level = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    result["maturity_signal"] = {
        "level": level,
        "score": score,
        "summary": "Maturity score recomputed after final cross-tier evidence consistency checks.",
    }
    result["maturity_semaphore"] = {
        item.get("label", item.get("id", "Section")): item.get("status")
        for item in sections
    }
    result["maturity_semaphore"]["Work vs Expected"] = level
    if isinstance(result.get("project_trend_evidence"), dict):
        result["project_trend_evidence"]["current_score"] = score


def apply_report_evidence_consistency_gate(result: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when report wording or scores outrun same-run evidence."""

    if result.get("status") != "complete":
        return result
    complexity_changed = _apply_complexity_gate(result)
    _reconcile_secret_history(result)
    if complexity_changed:
        _recompute_maturity(result)
    return result


__all__ = ["apply_report_evidence_consistency_gate"]
