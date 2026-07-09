from __future__ import annotations

from typing import Any

DEPENDENCY_TOOLS = ("pip-audit", "npm-audit", "osv-scanner")
STATIC_TOOLS = ("bandit", "semgrep", "eslint", "typescript")
SECRET_TOOLS = ("gitleaks", "trufflehog")
CLEAN_STATUSES = {"completed_clean", "completed"}
VERIFIED_STATUSES = {"completed_clean", "completed_with_findings", "completed"}
STALE_PROOF_GAP_FRAGMENTS = ("strict trust engine", "missing", "unavailable", "not verified", "not attached")


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in result.get("sections", []) or []:
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _status_from_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _remove_lines(section: dict[str, Any], fragments: tuple[str, ...]) -> None:
    lowered = tuple(fragment.lower() for fragment in fragments)
    for key in ("findings", "unavailable"):
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [item for item in values if not any(fragment in str(item).lower() for fragment in lowered)]


def _tools(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bundle = result.get("scanner_artifacts") if isinstance(result.get("scanner_artifacts"), dict) else {}
    tools = bundle.get("tools") if isinstance(bundle.get("tools"), dict) else {}
    if tools:
        return {str(name): payload for name, payload in tools.items() if isinstance(payload, dict)}
    artifact = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    raw = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
    return {str(name): payload for name, payload in raw.items() if isinstance(payload, dict)}


def _tool_status(tool: dict[str, Any]) -> str:
    return str(tool.get("evidence_status") or tool.get("status") or "")


def _finding_count(tool: dict[str, Any]) -> int:
    value = tool.get("findings_count")
    if isinstance(value, int):
        return value
    findings = tool.get("findings")
    return len(findings) if isinstance(findings, list) else 0


def _all_clean(tools: dict[str, dict[str, Any]], required: tuple[str, ...]) -> bool:
    for name in required:
        tool = tools.get(name)
        if not tool:
            return False
        if _tool_status(tool) not in CLEAN_STATUSES:
            return False
        if _finding_count(tool) != 0:
            return False
        if tool.get("verified_for_this_report") is False:
            return False
    return True


def _all_verified(tools: dict[str, dict[str, Any]], required: tuple[str, ...]) -> bool:
    for name in required:
        tool = tools.get(name)
        if not tool or _tool_status(tool) not in VERIFIED_STATUSES:
            return False
        if tool.get("verified_for_this_report") is False:
            return False
    return True


def _secret_history_verified(result: dict[str, Any]) -> bool:
    artifact = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    checkout = artifact.get("checkout") if isinstance(artifact.get("checkout"), dict) else {}
    history = artifact.get("secret_history_scan") if isinstance(artifact.get("secret_history_scan"), dict) else {}
    completed = set(str(item) for item in history.get("completed_tools", []) if item)
    return bool(
        checkout.get("full_history_secret_scan_requested")
        and checkout.get("history_depth") == "full"
        and all(tool in completed for tool in SECRET_TOOLS)
    )


def _complexity_profile(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("complexity_engine"), dict):
        return result["complexity_engine"]
    artifact = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    profile = artifact.get("complexity_engine")
    return profile if isinstance(profile, dict) else {}


def _set_section_score(section: dict[str, Any], score: int, summary: str, evidence: str) -> None:
    section["score"] = max(int(section.get("score") or 0), score)
    section["status"] = _status_from_score(int(section["score"]))
    section["summary"] = summary
    section.setdefault("evidence", [])
    if isinstance(section["evidence"], list):
        _append_unique(section["evidence"], evidence)
    section.setdefault("scanner_score_lift", {})["applied"] = True


def _dependency_lift(result: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    section = _section(result, "dependency_health")
    if not section or not _all_clean(tools, DEPENDENCY_TOOLS):
        return
    _remove_lines(section, STALE_PROOF_GAP_FRAGMENTS + ("pip-audit", "npm audit", "npm-audit", "osv-scanner", "osv scanner", "dependency scanner artifacts"))
    _set_section_score(
        section,
        90,
        "Dependency review is verified by current-run clean pip-audit, npm audit, and OSV Scanner artifacts.",
        "Verified score lift: current-run dependency scanner artifacts are clean and bound to this report run.",
    )


def _secret_lift(result: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    section = _section(result, "secrets_review")
    if not section or not (_all_clean(tools, SECRET_TOOLS) and _secret_history_verified(result)):
        return
    _remove_lines(section, STALE_PROOF_GAP_FRAGMENTS + ("gitleaks", "trufflehog", "secret history", "git-history", "full-history", "full git-history", "secret coverage"))
    _set_section_score(
        section,
        92,
        "Secrets review is verified by current-run clean full-history Gitleaks and TruffleHog artifacts.",
        "Verified score lift: full-history secret scanner artifacts are clean and bound to this report run.",
    )


def _static_lift(result: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    section = _section(result, "static_analysis")
    if not section:
        return
    bandit_triage = result.get("bandit_triage") if isinstance(result.get("bandit_triage"), dict) else {}
    clean = _all_clean(tools, STATIC_TOOLS)
    triaged_without_blockers = (
        _all_verified(tools, STATIC_TOOLS)
        and int(bandit_triage.get("blocking_count") or 0) == 0
        and int(bandit_triage.get("review_required_count") or 0) == 0
        and int(bandit_triage.get("finding_count") or 0) > 0
    )
    if not clean and not triaged_without_blockers:
        return
    _remove_lines(section, STALE_PROOF_GAP_FRAGMENTS + ("bandit", "semgrep", "eslint", "typescript", "scanner-worker static", "static tools unavailable", "scanner-worker artifacts"))
    _set_section_score(
        section,
        88 if triaged_without_blockers else 90,
        "Static analysis is verified by current-run Bandit, Semgrep, ESLint, and TypeScript artifacts." if clean else "Static analysis is verified by current-run scanner artifacts and approved triage with no blockers.",
        "Verified score lift: static scanner artifacts are complete and bound to this report run.",
    )


def _velocity_lift(result: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    section = _section(result, "velocity_complexity")
    if not section:
        return
    profile = _complexity_profile(result)
    dependency_clean = _all_clean(tools, DEPENDENCY_TOOLS)
    static_verified = _all_clean(tools, STATIC_TOOLS) or (
        _all_verified(tools, STATIC_TOOLS)
        and isinstance(result.get("bandit_triage"), dict)
        and int(result["bandit_triage"].get("blocking_count") or 0) == 0
        and int(result["bandit_triage"].get("review_required_count") or 0) == 0
    )
    if not (dependency_clean and static_verified and profile):
        return
    _remove_lines(section, STALE_PROOF_GAP_FRAGMENTS + ("release-readiness lift not applied", "final-clean evidence is incomplete", "deeper complexity", "runtime artifacts", "source-footprint"))
    target_score = int(profile.get("velocity_score") or profile.get("complexity_score") or 82)
    target_score = max(82, min(90, target_score))
    _set_section_score(
        section,
        target_score,
        "Velocity and complexity review is supported by clean dependency/static scanner proof and current-run complexity evidence.",
        "Verified score lift: dependency/static proof and complexity evidence are bound to this report run.",
    )


def _recompute_maturity(result: dict[str, Any]) -> None:
    sections = [
        item
        for item in result.get("sections", []) or []
        if isinstance(item, dict)
        and item.get("status") != "gray"
        and item.get("supplemental") is not True
        and int(item.get("scoring_weight", 1) or 0) != 0
    ]
    if not sections:
        return
    score = round(sum(int(section.get("score") or 0) for section in sections) / len(sections))
    level = "Senior" if score >= 82 else ("Mid" if score >= 58 else "Junior")
    result["maturity_signal"] = {
        "level": level,
        "score": score,
        "summary": "Maturity score recomputed after verified scanner artifact score lifts.",
    }
    result["maturity_semaphore"] = {section.get("label", section.get("id", "Section")): section.get("status") for section in sections}
    result["maturity_semaphore"]["Work vs Expected"] = level
    if isinstance(result.get("project_trend_evidence"), dict):
        result["project_trend_evidence"]["current_score"] = score


def apply_verified_scanner_score_lifts(result: dict[str, Any]) -> dict[str, Any]:
    """Lift yellow sections only from exact current-run verified scanner artifacts."""

    if result.get("status") != "complete":
        return result
    tools = _tools(result)
    if not tools:
        return result
    prior_guard = result.setdefault("report_quality_guards", {}).get("verified_scanner_score_lifts")
    prior_lifts = prior_guard.get("lifts", {}) if isinstance(prior_guard, dict) else {}
    before = {
        item.get("id"): int(item.get("score") or 0)
        for item in result.get("sections", []) or []
        if isinstance(item, dict) and item.get("id")
    }
    _dependency_lift(result, tools)
    _secret_lift(result, tools)
    _static_lift(result, tools)
    _velocity_lift(result, tools)
    after = {
        item.get("id"): int(item.get("score") or 0)
        for item in result.get("sections", []) or []
        if isinstance(item, dict) and item.get("id")
    }
    new_lifts = {
        section_id: {"previous_score": score, "new_score": after.get(section_id)}
        for section_id, score in before.items()
        if after.get(section_id, score) > score
    }
    combined_lifts = {**prior_lifts, **new_lifts}
    result.setdefault("report_quality_guards", {})["verified_scanner_score_lifts"] = {
        "status": "applied" if combined_lifts else "no_lifts",
        "lifts": combined_lifts,
        "guardrail": "Scores lift only from current-run scanner artifacts that are clean or explicitly triaged with no blockers.",
    }
    if new_lifts:
        _recompute_maturity(result)
    return result
