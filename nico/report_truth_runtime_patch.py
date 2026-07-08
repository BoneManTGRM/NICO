from __future__ import annotations

import re
from typing import Any

MALFORMED_EXTRA_OSV_RE = re.compile(
    r"OSV returned\s+(?P<count>\d+)\s+vulnerability record\(s\) for PyPI:(?P<name>[A-Za-z0-9_.-]+)@\[(?P<extra>[^\]]+)\]==(?P<version>[^:]+): (?P<ids>[^.]+)\.",
    re.IGNORECASE,
)


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in result.get("sections", []) or []
            if isinstance(item, dict) and item.get("id") == section_id
        ),
        None,
    )


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return str(value or "")


def _section_text(section: dict[str, Any] | None) -> str:
    if not section:
        return ""
    return "\n".join(_text(section.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _has_osv_vulnerabilities_text(text: str) -> bool:
    lower = text.lower()
    return "osv returned" in lower and "vulnerability record" in lower and "no vulnerability records" not in lower


def _has_osv_vulnerabilities(section: dict[str, Any] | None) -> bool:
    return _has_osv_vulnerabilities_text(_section_text(section))


def _has_malformed_extra_osv_query_text(text: str) -> bool:
    return bool(MALFORMED_EXTRA_OSV_RE.search(text))


def _has_malformed_extra_osv_query(section: dict[str, Any] | None) -> bool:
    return _has_malformed_extra_osv_query_text(_section_text(section))


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _status_from_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


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
    score = round(sum(int(item.get("score") or 0) for item in sections) / len(sections))
    level = "Senior" if score >= 82 else ("Mid" if score >= 58 else "Junior")
    summary = (
        "Evidence suggests mature delivery foundations with documented structure, automation, and low-risk signals, pending human validation."
        if score >= 82
        else "Evidence suggests useful foundations exist, but operating maturity depends on closing traceability, test, dependency, or automation gaps."
        if score >= 58
        else "Evidence suggests early-stage maturity or missing access to the signals needed for confident assessment."
    )
    result["maturity_signal"] = {"level": level, "score": score, "summary": summary}
    result["maturity_semaphore"] = {item.get("label", item.get("id", "Section")): item.get("status") for item in sections}
    result["maturity_semaphore"]["Work vs Expected"] = level


def _normalize_malformed_osv_extra_text(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_malformed_osv_extra_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_malformed_osv_extra_text(item) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        extra = match.group("extra")
        version = match.group("version")
        return (
            f"OSV query normalization required for PyPI:{name}[{extra}]=={version}: "
            "the PEP 508 extra was submitted as version text in earlier evidence, so those vulnerability IDs are not accepted as confirmed installed-package findings until normalized current-run pip-audit, npm audit, and OSV Scanner artifacts are attached."
        )

    return MALFORMED_EXTRA_OSV_RE.sub(replace, value)


def _strip_dependency_contradictions(dependency: dict[str, Any]) -> None:
    for key in ("evidence", "findings", "unavailable"):
        dependency[key] = [
            item
            for item in dependency.get(key, []) or []
            if "superseded earlier manifest-only dependency warnings" not in str(item).lower()
            and "this section cannot claim green 90" not in str(item).lower()
        ]


def apply_dependency_score_consistency(result: dict[str, Any]) -> dict[str, Any]:
    """Keep dependency scoring consistent with disclosed OSV findings.

    A dependency section may describe OSV or parsed audit evidence, but it must
    not remain GREEN 90 while the same report says OSV returned vulnerability
    records or while an OSV query was malformed by treating a PEP 508 extra as a
    version string.
    """

    raw_dependency = _section(result, "dependency_health")
    raw_text = _section_text(raw_dependency)
    had_malformed_query = _has_malformed_extra_osv_query_text(raw_text)
    had_osv_findings = _has_osv_vulnerabilities_text(raw_text)

    result["sections"] = _normalize_malformed_osv_extra_text(result.get("sections", []) or [])
    dependency = _section(result, "dependency_health")
    if not dependency:
        return result

    has_osv_findings = had_osv_findings or _has_osv_vulnerabilities(dependency)
    has_malformed_query = had_malformed_query or _has_malformed_extra_osv_query(dependency)
    if not (has_osv_findings or has_malformed_query):
        return result

    dependency.setdefault("findings", [])
    dependency.setdefault("unavailable", [])
    _strip_dependency_contradictions(dependency)
    if has_malformed_query:
        _append_unique(
            dependency["findings"],
            "Dependency score consistency guard: malformed OSV query evidence was detected, so this section cannot claim GREEN 90 until normalized current-run dependency artifacts prove the result.",
        )
    if has_osv_findings:
        _append_unique(
            dependency["findings"],
            "Dependency score consistency guard: OSV vulnerability records are present, so this section cannot claim GREEN 90 until current-run pip-audit, npm audit, and OSV Scanner artifacts prove the finding is resolved or not applicable.",
        )
    _append_unique(
        dependency["unavailable"],
        "Current-run scanner-clean dependency proof is required before any OSV finding or malformed OSV query can be treated as resolved or non-blocking.",
    )
    dependency["score"] = min(int(dependency.get("score") or 0), 74)
    dependency["status"] = _status_from_score(int(dependency["score"]))
    dependency["summary"] = "Dependency review found unresolved OSV or malformed OSV-query evidence; final scanner-clean status is not claimed until normalized current-run audit artifacts prove resolution or non-applicability."
    readiness = result.get("release_readiness")
    if isinstance(readiness, dict):
        missing = list(readiness.get("missing_signals") or [])
        for signal in ("dependency_scanner_clean_artifacts_attached", "dependency_no_osv_vulnerabilities"):
            if signal not in missing:
                missing.append(signal)
        readiness["status"] = "evidence_incomplete"
        readiness["missing_signals"] = missing
        readiness["passed_signals"] = [item for item in readiness.get("passed_signals", []) or [] if item not in set(missing)]
    _recompute_maturity(result)
    return result


def refresh_project_trend_score(result: dict[str, Any]) -> dict[str, Any]:
    trend = result.get("project_trend_evidence")
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    current_score = maturity.get("score")
    if not isinstance(trend, dict) or current_score is None:
        return result
    try:
        current_int = int(current_score)
    except (TypeError, ValueError):
        return result
    previous = trend.get("previous_score")
    average = trend.get("average_prior_score")
    trend["current_score"] = current_int
    trend["delta_from_previous"] = current_int - previous if isinstance(previous, int) else None
    trend["delta_from_average"] = current_int - average if isinstance(average, int) else None
    trend["non_regressing"] = bool(isinstance(previous, int) and isinstance(average, int) and current_int >= previous and current_int >= average)
    if trend.get("status") == "tracked":
        note = f"Project trend evidence: {trend.get('prior_run_count', 0)} prior completed Express run(s); previous score={previous}; prior average={average}; current score={current_int}; delta vs previous={trend.get('delta_from_previous')}."
    elif trend.get("status") == "baseline":
        note = f"Project trend baseline: 1 prior completed Express run; previous score={previous}; current score={current_int}. More runs are needed for a stable trend."
    else:
        note = "Project trend unavailable: no prior completed Express runs were found for this project in retained storage."
    trend["notes"] = [note]
    velocity = _section(result, "velocity_complexity")
    if velocity:
        velocity["evidence"] = [
            item
            for item in velocity.get("evidence", []) or []
            if not str(item).startswith(("Project trend evidence:", "Project trend baseline:", "Project trend unavailable:"))
        ]
        _append_unique(velocity["evidence"], note)
    return result


def rebuild_reports(result: dict[str, Any]) -> dict[str, Any]:
    """Rebuild report exports using the core finalizer's tolerant renderer."""

    from nico import final_report_consistency

    if result.get("status") != "complete":
        return result
    core_rebuild = getattr(final_report_consistency, "_rebuild_reports")
    core_rebuild(result)
    return result


def patch_final_report_consistency() -> None:
    from nico import final_report_consistency

    original = getattr(final_report_consistency, "_nico_original_finalize_express_result_consistency", None)
    if original is None:
        original = final_report_consistency.finalize_express_result_consistency
        final_report_consistency._nico_original_finalize_express_result_consistency = original

    def finalize_with_dependency_consistency(result: dict[str, Any]) -> dict[str, Any]:
        finalized = original(result)
        if finalized.get("status") != "complete":
            return finalized
        finalized = apply_dependency_score_consistency(finalized)
        finalized = refresh_project_trend_score(finalized)
        return rebuild_reports(finalized)

    final_report_consistency.finalize_express_result_consistency = finalize_with_dependency_consistency
