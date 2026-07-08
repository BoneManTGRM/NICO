from __future__ import annotations

from typing import Any


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


def apply_dependency_score_consistency(result: dict[str, Any]) -> dict[str, Any]:
    """Keep dependency scoring consistent with disclosed OSV findings.

    A dependency section may mention OSV findings as available evidence, but it must
    not remain GREEN 90 while the same report says OSV returned vulnerability
    records for an exact dependency query.
    """

    dependency = _section(result, "dependency_health")
    if not dependency or not _has_osv_vulnerabilities(dependency):
        return result
    dependency.setdefault("findings", [])
    dependency.setdefault("unavailable", [])
    _append_unique(
        dependency["findings"],
        "Dependency score consistency guard: OSV vulnerability records are present, so this section cannot claim GREEN 90 until current-run pip-audit, npm audit, and OSV Scanner artifacts prove the finding is resolved or not applicable.",
    )
    _append_unique(
        dependency["unavailable"],
        "Current-run scanner-clean dependency proof is required before any OSV finding can be treated as resolved or non-blocking.",
    )
    dependency["score"] = min(int(dependency.get("score") or 0), 74)
    dependency["status"] = _status_from_score(int(dependency["score"]))
    dependency["summary"] = "Dependency review found OSV vulnerability records from available manifest/OSV evidence; final scanner-clean status is not claimed until current-run audit artifacts prove resolution or non-applicability."
    _recompute_maturity(result)
    return result


def patch_final_report_consistency() -> None:
    from nico import final_report_consistency

    original = getattr(final_report_consistency, "_nico_original_finalize_express_result_consistency", None)
    if original is None:
        original = final_report_consistency.finalize_express_result_consistency
        final_report_consistency._nico_original_finalize_express_result_consistency = original

    def finalize_with_dependency_consistency(result: dict[str, Any]) -> dict[str, Any]:
        finalized = original(result)
        return apply_dependency_score_consistency(finalized)

    final_report_consistency.finalize_express_result_consistency = finalize_with_dependency_consistency
