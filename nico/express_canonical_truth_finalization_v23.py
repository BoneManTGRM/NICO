from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_canonical_truth_finalization.v23"
_PATCH_MARKER = "_nico_express_canonical_truth_finalization_v23"

_CLEAN_PATTERNS = (
    r"\bno vulnerabilit(?:y|ies)\b",
    r"\bfindings?=0\b",
    r"\bzero (?:dependency )?vulnerabilit(?:y|ies)\b",
    r"\bno secrets?\b",
    r"\bblocking=0\b",
    r"\bclean artifact",
)
_BAD_RUNTIME_PATTERNS = (
    r"\bstatus\s*[=:]\s*(?:failed|failure|timeout|timed[_ -]?out|unavailable|error)\b",
    r"\bended with status (?:failed|failure|timeout|timed[_ -]?out|unavailable|error)\b",
    r"\breturned (?:failed|failure|timeout|timed[_ -]?out|unavailable|error)\b",
    r"\brequired analyzer (?:did not complete|reported failure)\b",
    r"\bwas unavailable\b",
    r"\brequires human triage\b",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _is_clean(value: Any) -> bool:
    text = _text(value).casefold()
    return bool(text) and any(re.search(pattern, text, re.I) for pattern in _CLEAN_PATTERNS)


def _has_bad_runtime(section: dict[str, Any]) -> bool:
    values = [
        _text(value)
        for field in ("findings", "unavailable", "limitations")
        for value in (section.get(field) or [])
    ]
    haystack = " ".join(values).casefold()
    return any(re.search(pattern, haystack, re.I) for pattern in _BAD_RUNTIME_PATTERNS)


def _canonical_status(section: dict[str, Any]) -> tuple[str, str]:
    section_id = _text(section.get("id")).casefold()
    current_status = _text(section.get("status") or "unknown").casefold()
    current_confidence = _text(section.get("confidence") or "high")

    if section_id == "scanner_worker_evidence":
        return "supplemental", "review-limited"

    if section_id in {"client_acceptance", "client_human_acceptance"}:
        approved = bool(section.get("approved") or section.get("accepted"))
        score = section.get("score")
        if approved or current_status == "green" or (isinstance(score, (int, float)) and score > 0 and not section.get("unavailable")):
            return "green", current_confidence or "high"
        return "gray", "review-limited"

    if _has_bad_runtime(section):
        return "yellow", "review-limited"

    if current_status in {"green", "yellow", "red", "gray"}:
        return current_status, current_confidence
    return "green", current_confidence or "high"


def _normalize_scanner(section: dict[str, Any]) -> None:
    section["status"] = "supplemental"
    section["display_status"] = "SUPPLEMENTAL · NOT SCORED"
    section["directly_scored"] = False
    section["mapped_to_scored_controls"] = True
    section["presented_score"] = None
    section["score"] = None
    section["score_treatment"] = "supplemental_mapped_to_scored_controls"


def _remove_clean_promotions(section: dict[str, Any]) -> None:
    findings = section.get("findings")
    if isinstance(findings, list):
        section["findings"] = [value for value in findings if not _is_clean(value)]


def _resolve_dependency_contradiction(section: dict[str, Any]) -> None:
    evidence = " ".join(_text(value) for value in section.get("evidence") or []).casefold()
    findings = list(section.get("findings") or [])
    if "osv returned no vulnerability" in evidence:
        findings = [value for value in findings if not ("osv" in _text(value).casefold() and "finding" in _text(value).casefold())]
    section["findings"] = findings


def _resolve_secret_contradiction(section: dict[str, Any]) -> None:
    evidence = list(section.get("evidence") or [])
    findings = list(section.get("findings") or [])
    bad = " ".join(_text(value) for value in findings).casefold()
    if "gitleaks" in bad and "timeout" in bad:
        evidence = [value for value in evidence if not ("gitleaks" in _text(value).casefold() and "clean" in _text(value).casefold())]
    if "trufflehog" in bad and "triage" in bad:
        evidence = [value for value in evidence if not ("trufflehog" in _text(value).casefold() and ("zero credential" in _text(value).casefold() or "reported zero" in _text(value).casefold()))]
    section["evidence"] = evidence


def _resolve_static_contradiction(section: dict[str, Any]) -> None:
    findings = " ".join(_text(value) for value in section.get("findings") or []).casefold()
    evidence = list(section.get("evidence") or [])
    if "bandit" in findings and "failed" in findings:
        evidence = [value for value in evidence if not ("bandit" in _text(value).casefold() and "complete" in _text(value).casefold())]
    section["evidence"] = evidence


def _specific_todo_candidate(item: dict[str, Any]) -> bool:
    title = _text(item.get("title") or item.get("finding")).casefold()
    return "todo/fixme" in title or "security-note marker" in title


def _normalize_repair_intelligence(result: dict[str, Any]) -> None:
    intelligence = result.get("repair_intelligence")
    if not isinstance(intelligence, dict):
        return
    candidates = intelligence.get("candidates")
    if not isinstance(candidates, list):
        return
    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if _specific_todo_candidate(item):
            locations = [str(value) for value in item.get("affected_files") or [] if str(value).strip()]
            if not locations:
                continue
            item["business_impact"] = "Unresolved actionable markers at the listed source locations can hide incomplete behavior or security-sensitive follow-up work."
            item["recommended_action"] = "Review each exact marker in context, classify it as required work or intentional documentation, and remove or convert it to a tracked issue with an accountable owner."
            item["verification"] = "Confirm every retained marker has an explicit disposition, run focused tests for changed files, then regenerate the same-SHA assessment."
        normalized.append(item)
    intelligence["candidates"] = normalized
    intelligence["candidate_count"] = len(normalized)


def _remove_readme_only_dossier_evidence(result: dict[str, Any]) -> None:
    for key in ("finding_dossiers", "dossiers"):
        dossiers = result.get(key)
        if not isinstance(dossiers, list):
            continue
        for dossier in dossiers:
            if not isinstance(dossier, dict):
                continue
            evidence = list(dossier.get("evidence") or [])
            dossier["evidence"] = [value for value in evidence if "readme.md is present" not in _text(value).casefold()]


def _canonicalize_sections(result: dict[str, Any]) -> None:
    sections = result.get("sections")
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, dict):
            continue
        _remove_clean_promotions(section)
        section_id = _text(section.get("id")).casefold()
        if section_id == "dependency_health":
            _resolve_dependency_contradiction(section)
        elif section_id == "secrets_review":
            _resolve_secret_contradiction(section)
        elif section_id == "static_analysis":
            _resolve_static_contradiction(section)
        if section_id == "scanner_worker_evidence":
            _normalize_scanner(section)
        status, confidence = _canonical_status(section)
        section["status"] = status
        section["confidence"] = confidence


def _rewrite_markdown_statuses(markdown: str, result: dict[str, Any]) -> str:
    output = markdown
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = _text(section.get("label") or section.get("title"))
        if not label:
            continue
        status = _text(section.get("status")).upper()
        if _text(section.get("id")).casefold() == "scanner_worker_evidence":
            output = re.sub(rf"(###\s+{re.escape(label)}\s+—\s+)[A-Z]+\s*\([^\n]+\)", rf"\1SUPPLEMENTAL (NOT SCORED)", output)
            output = re.sub(rf"(-\s+\*\*{re.escape(label)}\*\*:\s*)\w+", rf"\1supplemental", output, flags=re.I)
            continue
        output = re.sub(rf"(###\s+{re.escape(label)}\s+—\s+)[A-Z]+(\s*\([^\n]+\))", rf"\1{status}\2", output)
        output = re.sub(rf"(-\s+\*\*{re.escape(label)}\*\*:\s*)\w+", rf"\1{status.casefold()}", output, flags=re.I)
    return output


def finalize_express_truth(result: dict[str, Any]) -> dict[str, Any]:
    _canonicalize_sections(result)
    _normalize_repair_intelligence(result)
    _remove_readme_only_dossier_evidence(result)
    reports = result.get("reports")
    if isinstance(reports, dict) and isinstance(reports.get("markdown"), str):
        reports["markdown"] = _rewrite_markdown_statuses(reports["markdown"], result)
    result["express_canonical_truth_finalization"] = {
        "status": "complete",
        "version": VERSION,
        "scanner_supplemental_not_scored": True,
        "markdown_statuses_canonical": True,
        "failed_analyzer_green_contradiction_blocked": True,
        "clean_evidence_promotion_blocked": True,
        "dependency_contradiction_reconciled": True,
        "secret_contradiction_reconciled": True,
        "static_contradiction_reconciled": True,
        "generic_todo_candidate_blocked_without_location": True,
        "readme_only_dossier_evidence_removed": True,
        "human_review_required": True,
    }
    return result


def install_express_canonical_truth_finalization_v23() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        finalize_express_truth(result)
        return current(result)

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {"status": "installed", "version": VERSION, "production_renderer_bound": True}


__all__ = ["VERSION", "finalize_express_truth", "install_express_canonical_truth_finalization_v23"]
