from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_decision_quality.v17"
_PATCH_MARKER = "_nico_express_decision_quality_v17"
_SCRIPT_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_SIZE_ADVISORY_TERMS = (
    "source-file footprint is large",
    "total source loc is high",
    "repository size",
    "increases review scope",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _key(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"\b(?:architecture_debt|velocity_complexity)\b", "", text)
    return re.sub(r"\W+", " ", text).strip()


def _is_language_false_positive(value: Any) -> bool:
    text = _text(value).casefold()
    return "python_eval_exec" in text and any(ext in text for ext in _SCRIPT_EXTENSIONS)


def _reconcile_ci_statement(value: str) -> str:
    match = re.search(
        r"(?P<total>\d+)\s*;\s*success=(?P<success>\d+)\s*;\s*non-success=(?P<non>\d+)",
        value,
        re.I,
    )
    if not match:
        return value
    total = int(match.group("total"))
    success = int(match.group("success"))
    non_success = int(match.group("non"))
    other = max(0, total - success - non_success)
    replacement = f"{total}; success={success}; non-success={non_success}; other/unknown={other}"
    return value[: match.start()] + replacement + value[match.end() :]


def _normalize_sections(result: dict[str, Any]) -> None:
    sections = result.get("sections")
    if not isinstance(sections, list):
        return
    seen_findings: set[str] = set()
    normalized: list[dict[str, Any]] = []
    preferred_order = {"architecture_debt": 0, "velocity_complexity": 1}
    ordered = sorted(
        (deepcopy(item) for item in sections if isinstance(item, dict)),
        key=lambda item: preferred_order.get(str(item.get("id") or ""), -1),
    )
    for section in ordered:
        for field in ("evidence", "findings", "unavailable"):
            values = section.get(field)
            if not isinstance(values, list):
                continue
            output: list[str] = []
            local_seen: set[str] = set()
            for raw in values:
                text = _reconcile_ci_statement(_text(raw))
                if not text or _is_language_false_positive(text):
                    continue
                semantic = _key(text)
                if semantic in local_seen:
                    continue
                if field == "findings" and semantic in seen_findings:
                    continue
                local_seen.add(semantic)
                if field == "findings":
                    seen_findings.add(semantic)
                output.append(text)
            section[field] = output
        normalized.append(section)
    result["sections"] = normalized


def _group_unverified_secret_candidates(result: dict[str, Any]) -> None:
    intelligence = result.get("repair_intelligence")
    if not isinstance(intelligence, dict):
        return
    candidates = intelligence.get("candidates")
    if not isinstance(candidates, list):
        return
    retained: list[dict[str, Any]] = []
    secret_candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        title = _text(item.get("title") or item.get("finding"))
        status = _text(item.get("status")).casefold()
        category = _text(item.get("category")).casefold()
        verified = bool(item.get("verified_fix")) or status in {"verified", "confirmed", "validated"}
        if category == "secret_exposure" and not verified:
            secret_candidates.append(item)
            continue
        semantic = _key(title)
        if semantic and semantic not in seen:
            seen.add(semantic)
            retained.append(item)
    if secret_candidates:
        files: list[str] = []
        evidence: list[str] = []
        for item in secret_candidates:
            for path in item.get("affected_files") or []:
                if path not in files:
                    files.append(path)
            for value in item.get("evidence") or []:
                text = _text(value)
                if text and text not in evidence:
                    evidence.append(text)
        retained.append(
            {
                "candidate_id": "express_secret_candidate_triage_group",
                "category": "secret_candidate_triage",
                "title": f"Triage {len(secret_candidates)} unverified secret-scan candidate(s) as one workstream",
                "severity": "review",
                "confidence": "review-limited",
                "status": "candidate_pending_human_triage",
                "priority": "review",
                "effort": "small",
                "affected_files": files,
                "evidence": evidence[:8],
                "business_impact": "No credential exposure is established until exact values, rules, locations, and scanner dispositions are reviewed.",
                "recommended_action": "Triage all related candidates in parallel, suppress synthetic or generic token-name matches, and escalate only confirmed credentials.",
                "verification": "Record a disposition for every candidate, rerun current-tree and history scanners, and confirm that only verified findings enter executive priority sections.",
                "human_review_required": True,
                "automatic_application_allowed": False,
                "verified_fix": False,
            }
        )
    intelligence["candidates"] = retained
    intelligence["candidate_count"] = len(retained)
    result["repair_intelligence"] = intelligence


def _canonicalize_summary(result: dict[str, Any]) -> None:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    score = maturity.get("score", result.get("technical_score"))
    level = maturity.get("level") or maturity.get("label") or "Unclassified"
    repository = result.get("repository") or "the authorized repository"
    result["executive_summary"] = (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repository}. "
        f"The canonical source maturity signal is {level} ({score}/100). The evidence-adjusted score is reported separately, "
        "and client delivery remains blocked pending exact-snapshot human review."
    )


def normalize_express_decision_quality(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    _normalize_sections(output)
    _group_unverified_secret_candidates(output)
    _canonicalize_summary(output)
    output["express_decision_quality"] = {
        "status": "normalized",
        "version": VERSION,
        "language_false_positives_removed": True,
        "cross_section_findings_deduplicated": True,
        "ci_counts_reconciled": True,
        "unverified_secret_candidates_grouped": True,
        "canonical_summary_bound": True,
    }
    return output


def _apply_normalized_result_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    """Apply report normalization without replacing nested containers held by outer renderers."""
    existing_reports = result.get("reports")
    for key, value in normalized.items():
        if key == "reports" and isinstance(existing_reports, dict) and isinstance(value, dict):
            existing_reports.clear()
            existing_reports.update(value)
            result["reports"] = existing_reports
        else:
            result[key] = value


def _classify_dossier(dossier: Any) -> Any:
    title = _text(getattr(dossier, "title", "")).casefold()
    severity = "review"
    if any(term in title for term in ("failed", "timeout", "vulnerability", "exposure")):
        severity = "high"
    elif any(term in title for term in ("complexity", "hotspot", "high churn", "ownership concentration")):
        severity = "medium"
    if any(term in title for term in _SIZE_ADVISORY_TERMS):
        severity = "informational"
    try:
        return replace(dossier, severity=severity)
    except Exception:
        return dossier


def install_express_decision_quality_v17() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_report_dossier_export_v15 as dossier_export

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    render_status = "already_installed"
    if not getattr(current, _PATCH_MARKER, False):
        @wraps(current)
        def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
            normalized = normalize_express_decision_quality(result)
            _apply_normalized_result_in_place(result, normalized)
            return current(result)

        setattr(render, _PATCH_MARKER, True)
        setattr(render, "_nico_previous", current)
        assessment_quality._build_polished_pdf_base64 = render
        render_status = "installed"

    original_builder = dossier_export.build_finding_dossiers
    dossier_status = "already_installed"
    if not getattr(original_builder, _PATCH_MARKER, False):
        @wraps(original_builder)
        def classified_dossiers(result: dict[str, Any]) -> list[Any]:
            output: list[Any] = []
            seen: set[str] = set()
            for dossier in original_builder(result):
                semantic = _key(getattr(dossier, "title", ""))
                if not semantic or semantic in seen:
                    continue
                seen.add(semantic)
                output.append(_classify_dossier(dossier))
            return output

        setattr(classified_dossiers, _PATCH_MARKER, True)
        setattr(classified_dossiers, "_nico_previous", original_builder)
        dossier_export.build_finding_dossiers = classified_dossiers
        dossier_status = "installed"

    return {
        "status": "installed" if "installed" in {render_status, dossier_status} else "already_installed",
        "version": VERSION,
        "render_binding": render_status,
        "dossier_binding": dossier_status,
    }


__all__ = ["VERSION", "install_express_decision_quality_v17", "normalize_express_decision_quality"]
