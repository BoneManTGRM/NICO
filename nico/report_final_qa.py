from __future__ import annotations

import re
from typing import Any

MALFORMED_OSV_EXTRA_RE = re.compile(
    r"OSV returned\s+(?P<count>\d+)\s+vulnerability record\(s\) for PyPI:(?P<name>[A-Za-z0-9_.-]+)@\[(?P<extra>[^\]]+)\]==(?P<version>[^:]+): (?P<ids>[^.]+)\.",
    re.IGNORECASE,
)
BANDIT_TRIAGE_RE = re.compile(r"Bandit(?: artifact)? reported\s+(?P<count>\d+)\s+finding", re.IGNORECASE)


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


def _find_section(result: dict[str, Any], *needles: str) -> dict[str, Any] | None:
    wanted = [needle.lower() for needle in needles if needle]
    for item in result.get("sections", []) or []:
        if not isinstance(item, dict):
            continue
        haystack = f"{item.get('id', '')} {item.get('label', '')}".lower()
        if all(needle in haystack for needle in wanted):
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


def _set_score(section: dict[str, Any], score: int) -> None:
    score = max(0, min(100, int(score)))
    section["score"] = score
    section["status"] = _status_from_score(score)


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
            "the PEP 508 extra was previously submitted as version text, so this malformed OSV response is not accepted as confirmed installed-package vulnerability evidence. "
            "Attach normalized current-run pip-audit, npm audit, and OSV Scanner artifacts before claiming scanner-clean dependency status."
        )

    return MALFORMED_OSV_EXTRA_RE.sub(replace, value)


def _has_confirmed_osv_vulnerability_text(text: str) -> bool:
    lower = text.lower()
    if "no vulnerability records" in lower:
        return False
    if "osv returned" not in lower or "vulnerability record" not in lower:
        return False
    return "@[" not in text


def _has_malformed_osv_extra_text(text: str) -> bool:
    return bool(MALFORMED_OSV_EXTRA_RE.search(text)) or "osv query normalization required" in text.lower()


def _remove_green_summary_claim(summary: str) -> str:
    text = str(summary or "")
    text = re.sub(r"\bis green\b", "requires review", text, flags=re.IGNORECASE)
    text = re.sub(r"\bgreen from\b", "review-limited from", text, flags=re.IGNORECASE)
    return text


def _apply_dependency_qa(result: dict[str, Any]) -> None:
    dependency = _find_section(result, "dependency")
    if not dependency:
        return

    raw_text = _section_text(dependency)
    had_malformed = _has_malformed_osv_extra_text(raw_text)
    result["sections"] = _normalize_malformed_osv_extra_text(result.get("sections", []) or [])
    dependency = _find_section(result, "dependency")
    if not dependency:
        return
    normalized_text = _section_text(dependency)
    confirmed_osv = _has_confirmed_osv_vulnerability_text(normalized_text)
    unresolved_osv_status = "completed_with_findings" in normalized_text.lower()

    if not (had_malformed or confirmed_osv or unresolved_osv_status):
        return

    dependency.setdefault("findings", [])
    dependency.setdefault("unavailable", [])
    dependency["summary"] = (
        "Dependency review is not scanner-clean: OSV evidence, malformed OSV-query evidence, or unresolved dependency-audit status remains. "
        "Current-run pip-audit, npm audit, and OSV Scanner artifacts are required before any green dependency claim."
    )
    dependency["findings"] = [
        item
        for item in dependency.get("findings", []) or []
        if "superseded earlier manifest-only dependency warnings" not in str(item).lower()
    ]
    if confirmed_osv:
        _append_unique(
            dependency["findings"],
            "Final report QA guard: confirmed OSV vulnerability records are present, so Dependency cannot be GREEN until current-run scanner-clean artifacts prove remediation or non-applicability.",
        )
        _set_score(dependency, min(int(dependency.get("score") or 0), 68))
    else:
        _append_unique(
            dependency["findings"],
            "Final report QA guard: malformed or unresolved OSV dependency evidence is present, so Dependency cannot be GREEN until normalized scanner-clean artifacts are attached.",
        )
        _set_score(dependency, min(int(dependency.get("score") or 0), 74))
    _append_unique(
        dependency["unavailable"],
        "Current-run pip-audit, npm audit, and OSV Scanner artifacts must be attached and verified before dependency scanner-clean or green status can be claimed.",
    )


def _apply_static_qa(result: dict[str, Any]) -> None:
    static = _find_section(result, "static")
    if not static:
        return
    text = _section_text(static)
    lower = text.lower()
    bandit_count = 0
    match = BANDIT_TRIAGE_RE.search(text)
    if match:
        bandit_count = int(match.group("count") or 0)
    untriaged_bandit = bandit_count > 0 and (
        "review_required_count" in lower
        or "requires explicit triage" in lower
        or "needs_human_review" in lower
        or "live scanner-worker bandit execution is not verified" in lower
    )
    if not untriaged_bandit:
        return
    static.setdefault("findings", [])
    static.setdefault("unavailable", [])
    static["summary"] = (
        f"Static analysis is review-limited: Bandit artifact evidence reports {bandit_count} finding(s), and live scanner-worker Bandit/Semgrep/ESLint/TypeScript proof is not attached. "
        "This section cannot be GREEN until rule-level triage is approved."
    )
    _append_unique(
        static["findings"],
        f"Final report QA guard: {bandit_count} untriaged Bandit finding(s) require human review, so Static Analysis cannot be GREEN until triage evidence is attached and approved.",
    )
    _append_unique(
        static["unavailable"],
        "Approved Bandit/Semgrep/ESLint/TypeScript scanner-worker artifacts and rule-level triage are required before final static scanner-clean or green status can be claimed.",
    )
    _set_score(static, min(int(static.get("score") or 0), 74))


def _remove_inconsistent_green_wording(result: dict[str, Any]) -> None:
    for item in result.get("sections", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "green" or int(item.get("score") or 0) < 75:
            item["summary"] = _remove_green_summary_claim(str(item.get("summary") or ""))


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
    if isinstance(result.get("project_trend_evidence"), dict):
        result["project_trend_evidence"]["current_score"] = score


def apply_final_report_qa(result: dict[str, Any]) -> dict[str, Any]:
    """Final invariant pass for client-visible report truth.

    This pass is intentionally stricter than scoring heuristics. It prevents the
    final JSON, Markdown, HTML, and PDF from showing green status when the same
    section discloses unresolved OSV dependency evidence or untriaged Bandit
    findings.
    """

    if result.get("status") != "complete":
        return result
    _apply_dependency_qa(result)
    _apply_static_qa(result)
    _remove_inconsistent_green_wording(result)
    _recompute_maturity(result)
    result.setdefault("report_quality_guards", {})["final_report_qa"] = {
        "status": "applied",
        "rules": [
            "dependency_not_green_with_osv_or_malformed_osv_evidence",
            "static_not_green_with_untriaged_bandit_findings",
            "no_yellow_or_red_section_summary_claims_green",
            "maturity_score_recomputed_after_final_qa",
        ],
    }
    return result


def patch_polish_express_result_for_final_qa() -> None:
    from nico import assessment_quality

    original = getattr(assessment_quality, "_nico_original_polish_express_result", None)
    if original is None:
        original = assessment_quality.polish_express_result
        assessment_quality._nico_original_polish_express_result = original

    def polish_express_result_with_final_qa(result: dict[str, Any]) -> dict[str, Any]:
        return apply_final_report_qa(original(result))

    assessment_quality.polish_express_result = polish_express_result_with_final_qa
