from __future__ import annotations

import re
from datetime import datetime, timezone
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


def _has_osv_vulnerabilities(section: dict[str, Any] | None) -> bool:
    text = _section_text(section).lower()
    return "osv returned" in text and "vulnerability record" in text and "no vulnerability records" not in text


def _has_malformed_extra_osv_query(section: dict[str, Any] | None) -> bool:
    return bool(MALFORMED_EXTRA_OSV_RE.search(_section_text(section)))


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

    result["sections"] = _normalize_malformed_osv_extra_text(result.get("sections", []) or [])
    dependency = _section(result, "dependency_health")
    if not dependency:
        return result

    has_osv_findings = _has_osv_vulnerabilities(dependency)
    has_malformed_query = _has_malformed_extra_osv_query(dependency) or "@ [" in _section_text(dependency)
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
        result["release_readiness"]["passed_signals"] = [
            item for item in readiness.get("passed_signals", []) or [] if item not in set(missing)
        ]
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_report_defaults(result: dict[str, Any]) -> None:
    """Make report rebuilding safe for partial unit-test payloads.

    The finalizer is used by both full hosted assessment results and narrow unit
    tests that intentionally omit report-only metadata. Rebuilding reports must
    not make those partial payloads crash.
    """

    from nico.hosted_assessment import SERVICE_TARGETS

    result.setdefault("generated_at", _utc_now())
    result.setdefault("repository", result.get("source_scope") or "authorized repository")
    result.setdefault("client_name", "")
    result.setdefault("project_name", result.get("repository") or "NICO")
    result.setdefault("assessment_mode", "express")
    result.setdefault("coverage_targets", SERVICE_TARGETS)
    result.setdefault("sections", [])
    result.setdefault("findings", [])
    result.setdefault("quick_wins", [])
    result.setdefault("medium_term_plan", [])
    result.setdefault("resourcing_recommendation", [])
    result.setdefault("risk_register", [])
    result.setdefault("verification_checklist", [])
    result.setdefault("reports", {})
    if not isinstance(result.get("maturity_signal"), dict):
        result["maturity_signal"] = {"level": "Unknown", "score": "N/A"}


def rebuild_reports(result: dict[str, Any]) -> dict[str, Any]:
    from nico.hosted_assessment import build_html, build_markdown, build_pdf_base64
    from nico.i18n_es_mx import reports_es_mx, wants_es_mx

    _ensure_report_defaults(result)
    result["executive_summary"] = (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {result.get('repository') or result.get('source_scope') or 'the authorized repository'}. "
        f"The final maturity signal is {(result.get('maturity_signal') or {}).get('level', 'Unknown')} ({(result.get('maturity_signal') or {}).get('score', 'N/A')}/100). "
        "Scores are generated from the final evidence-bound result after code audit, dependency, secrets, static analysis, CI/CD, architecture, velocity, artifact evidence, retained project history when available, acceptance when approved, and explicit unavailable-data notes have been applied. Final delivery still requires human review."
    )
    result["reports"] = {
        "markdown": build_markdown(result),
        "html": build_html(result),
        "pdf_base64": build_pdf_base64(result),
    }
    if any(wants_es_mx(result.get(key)) for key in ("report_language", "language", "assessment_mode")):
        result["reports"].update(reports_es_mx(result))
    return result


def patch_final_report_consistency() -> None:
    from nico import final_report_consistency

    original = getattr(final_report_consistency, "_nico_original_finalize_express_result_consistency", None)
    if original is None:
        original = final_report_consistency.finalize_express_result_consistency
        final_report_consistency._nico_original_finalize_express_result_consistency = original

    def finalize_with_dependency_consistency(result: dict[str, Any]) -> dict[str, Any]:
        finalized = original(result)
        finalized = apply_dependency_score_consistency(finalized)
        finalized = refresh_project_trend_score(finalized)
        return rebuild_reports(finalized)

    final_report_consistency.finalize_express_result_consistency = finalize_with_dependency_consistency
