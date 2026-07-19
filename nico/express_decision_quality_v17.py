from __future__ import annotations

import copy
import re
from copy import deepcopy
from dataclasses import is_dataclass, replace
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_decision_quality.v20_batch_c_fix2"
_PATCH_MARKER = "_nico_express_decision_quality_v20_batch_c"
_SCRIPT_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_SIZE_ADVISORY_TERMS = (
    "source-file footprint is large",
    "total source loc is high",
    "repository size",
    "increases review scope",
)
_CLEAN_EVIDENCE_PATTERNS = (
    r"\bno vulnerabilit(?:y|ies) (?:record|records|found|detected|reported)\b",
    r"\breturned no vulnerabilit(?:y|ies)\b",
    r"\b(?:found|returned|reported|detected) no vulnerabilit(?:y|ies)\b",
    r"\b0 vulnerabilit(?:y|ies)\b",
    r"\bno secrets? (?:found|detected|reported)\b",
    r"\b(?:found|returned|reported|detected) no secrets?\b",
    r"\b0 secrets?\b",
    r"\bno credential(?:s)? (?:found|detected|reported)\b",
    r"\b(?:found|returned|reported|detected) no credentials?\b",
    r"\bclean (?:credential|secret|dependency|scanner|scan|artifact)\b",
    r"\bblocking=0\b",
    r"\bfindings?=0\b",
    r"\bpassed with no findings\b",
)
_CI_ALIASES = {
    "success": "success",
    "succeeded": "success",
    "failure": "failure",
    "failed": "failure",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "skipped": "skipped",
    "neutral": "neutral",
    "timed-out": "timed_out",
    "timed_out": "timed_out",
    "timeout": "timed_out",
    "action-required": "action_required",
    "action_required": "action_required",
    "stale": "stale",
    "startup-failure": "startup_failure",
    "startup_failure": "startup_failure",
    "non-success": "non_success",
    "other/unknown": "unknown",
    "other": "unknown",
    "unknown": "unknown",
}
_CI_DETAIL_ORDER = (
    "success",
    "failure",
    "cancelled",
    "skipped",
    "neutral",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
    "unknown",
)
_INTERNAL_SCORE_KEYS = {"bar", "glyph_bar", "contribution_bar", "bar_geometry", "bar_render_mode"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _key(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"\b(?:architecture_debt|velocity_complexity)\b", "", text)
    return re.sub(r"\W+", " ", text).strip()


def _is_language_false_positive(value: Any) -> bool:
    text = _text(value).casefold()
    return ("python_eval_exec" in text or "python eval exec" in text) and any(ext in text for ext in _SCRIPT_EXTENSIONS)


def _is_clean_evidence(value: Any) -> bool:
    text = _text(value).casefold()
    return bool(text) and any(re.search(pattern, text, re.I) for pattern in _CLEAN_EVIDENCE_PATTERNS)


def _canonical_ci_categories(total: int, pairs: list[tuple[str, int]]) -> dict[str, int]:
    categories: dict[str, int] = {}
    aggregate_non_success = 0
    explicit_unknown = 0
    for raw_label, raw_count in pairs:
        label = _CI_ALIASES.get(raw_label.casefold().strip().replace(" ", "-"))
        if not label:
            continue
        count = max(0, int(raw_count))
        if label == "non_success":
            aggregate_non_success = max(aggregate_non_success, count)
        elif label == "unknown":
            explicit_unknown = max(explicit_unknown, count)
        else:
            categories[label] = categories.get(label, 0) + count
    detailed_non_success = sum(categories.get(label, 0) for label in _CI_DETAIL_ORDER if label != "success")
    categories["unknown"] = explicit_unknown
    if aggregate_non_success and not detailed_non_success and not explicit_unknown:
        categories["unknown"] = max(0, total - categories.get("success", 0) - aggregate_non_success)
    accounted = sum(categories.values())
    categories["unknown"] += max(0, total - accounted)
    overflow = sum(categories.values()) - total
    if overflow > 0:
        categories["unknown"] = max(0, categories["unknown"] - overflow)
    return categories


def _reconcile_ci_statement(value: str) -> str:
    if "workflow runs" not in value.casefold():
        return value
    match = re.search(r"(?P<total>\d+)\s*;(?P<body>(?:\s*[A-Za-z][A-Za-z _/-]*=\d+\s*;?)*)", value, re.I)
    if not match:
        return value
    total = int(match.group("total"))
    pairs = [(label.strip(), int(count)) for label, count in re.findall(r"([A-Za-z][A-Za-z _/-]*)=(\d+)", match.group("body"))]
    if not pairs:
        return value
    normalized_pairs = [(_CI_ALIASES.get(label.casefold().strip().replace(" ", "-")), count) for label, count in pairs]
    supplied = {label for label, _ in normalized_pairs if label}
    if supplied.issubset({"success", "non_success", "unknown"}):
        success = max((count for label, count in normalized_pairs if label == "success"), default=0)
        non_success = max((count for label, count in normalized_pairs if label == "non_success"), default=0)
        explicit_unknown = max((count for label, count in normalized_pairs if label == "unknown"), default=0)
        inferred_unknown = max(0, total - success - non_success)
        other = max(explicit_unknown, inferred_unknown)
        replacement = f"{total}; success={success}; non-success={non_success}; other/unknown={other}"
    else:
        categories = _canonical_ci_categories(total, pairs)
        rendered = [f"{label}={categories.get(label, 0)}" for label in _CI_DETAIL_ORDER if label != "unknown"]
        rendered.append(f"other/unknown={categories.get('unknown', 0)}")
        replacement = f"{total}; " + "; ".join(rendered)
    return value[: match.start()] + replacement + value[match.end() :]


def _score_value(item: dict[str, Any]) -> float | None:
    for key in ("presented_score", "presented", "score", "points", "contribution"):
        raw = item.get(key)
        if isinstance(raw, str):
            raw = raw.split("/", 1)[0]
        try:
            if raw is not None and str(raw).strip() != "":
                return float(raw)
        except (TypeError, ValueError):
            pass
    return None


def _proportional_bar(score: Any, slots: int = 20) -> str:
    try:
        numeric = max(0.0, min(100.0, float(score)))
    except (TypeError, ValueError):
        numeric = 0.0
    filled = 0 if numeric == 0 else max(1, round(slots * numeric / 100.0))
    return "■" * filled + "□" * (slots - filled)


def _normalize_score_objects(value: Any, seen: set[int] | None = None) -> None:
    if seen is None:
        seen = set()
    if not isinstance(value, (dict, list)):
        return
    identity = id(value)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(value, list):
        for child in list(value):
            _normalize_score_objects(child, seen)
        return
    original_children = [(key, child) for key, child in list(value.items()) if key not in _INTERNAL_SCORE_KEYS]
    label = _text(value.get("control") or value.get("title") or value.get("name") or value.get("label"))
    score = _score_value(value)
    if score is not None:
        value["bar"] = _proportional_bar(score)
        value["glyph_bar"] = value["bar"]
        value["contribution_bar"] = value["bar"]
        value["bar_geometry"] = {"value": score, "maximum": 100.0, "ratio": max(0.0, min(1.0, score / 100.0)), "width": max(0.0, min(120.0, score * 1.2))}
        value["bar_render_mode"] = "proportional_geometry"
    if label.casefold() == "scanner worker evidence":
        value.update({"directly_scored": False, "mapped_to_scored_controls": True, "score_treatment": "supplemental_mapped_to_scored_controls", "display_status": "SUPPLEMENTAL · MAPPED TO SCORED CONTROLS", "status": "SUPPLEMENTAL", "presented_score": None, "presented": None, "bar": _proportional_bar(0), "glyph_bar": _proportional_bar(0), "contribution_bar": _proportional_bar(0), "bar_geometry": {"value": 0.0, "maximum": 100.0, "ratio": 0.0, "width": 0.0}})
    for _, child in original_children:
        _normalize_score_objects(child, seen)


def _normalize_sections(result: dict[str, Any]) -> None:
    sections = result.get("sections")
    if not isinstance(sections, list):
        return
    seen_findings: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw_section in sections:
        if not isinstance(raw_section, dict):
            continue
        section = deepcopy(raw_section)
        section_id = str(section.get("id") or "")
        if section_id == "velocity_complexity":
            section.update({"page_break_before": True, "pdf_page_break_before": True, "decision_record_boundary": "new_page"})
        if section_id == "scanner_worker_evidence":
            section.update({"directly_scored": False, "mapped_to_scored_controls": True, "display_status": "SUPPLEMENTAL · MAPPED TO SCORED CONTROLS", "status": "SUPPLEMENTAL"})
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
                if field == "findings" and _is_clean_evidence(text):
                    continue
                semantic = _key(text)
                if semantic in local_seen or (field == "findings" and semantic in seen_findings):
                    continue
                local_seen.add(semantic)
                if field == "findings":
                    seen_findings.add(semantic)
                output.append(text)
            section[field] = output
        normalized.append(section)
    result["sections"] = normalized


def _candidate_is_verified(item: dict[str, Any]) -> bool:
    status = _text(item.get("status")).casefold()
    disposition = _text(item.get("disposition")).casefold()
    return bool(item.get("verified_fix") or item.get("verified_finding")) or status in {"verified", "confirmed", "validated"} or disposition in {"verified", "confirmed", "validated"}


def _candidate_contains_clean_evidence(item: dict[str, Any]) -> bool:
    values = [item.get("title"), item.get("finding"), item.get("business_impact"), item.get("recommended_action"), *(item.get("evidence") or [])]
    return any(_is_clean_evidence(value) for value in values)


def _normalize_repair_candidates(result: dict[str, Any]) -> None:
    intelligence = result.get("repair_intelligence")
    if not isinstance(intelligence, dict) or not isinstance(intelligence.get("candidates"), list):
        return
    retained: list[dict[str, Any]] = []
    secret_candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in intelligence["candidates"]:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        title = _text(item.get("title") or item.get("finding"))
        category = _text(item.get("category")).casefold()
        if _is_language_false_positive(title) or any(_is_language_false_positive(value) for value in item.get("evidence") or []):
            continue
        if _candidate_contains_clean_evidence(item):
            continue
        verified = _candidate_is_verified(item)
        if category == "secret_exposure" and not verified:
            secret_candidates.append(item)
            continue
        if not verified and _text(item.get("severity")).casefold() in {"critical", "high"}:
            item.update({"severity": "review", "priority": "review", "confidence": "review-limited", "classification": "review_limited"})
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
        retained.append({"candidate_id": "express_secret_candidate_triage_group", "category": "secret_candidate_triage", "title": f"Triage {len(secret_candidates)} unverified secret-scan candidate(s) as one parallel workstream", "severity": "review", "classification": "review_limited", "confidence": "review-limited", "status": "candidate_pending_human_triage", "priority": "review", "effort": "small", "affected_files": files, "evidence": evidence[:8], "business_impact": "No credential exposure is established until exact values, rules, locations, and scanner dispositions are reviewed.", "recommended_action": "Triage all related candidates in parallel, suppress synthetic or generic token-name matches, and escalate only confirmed credentials.", "verification": "Record a disposition for every candidate, rerun current-tree and history scanners, and confirm that only verified findings enter executive priority sections.", "human_review_required": True, "automatic_application_allowed": False, "verified_fix": False})
    intelligence["candidates"] = retained
    intelligence["candidate_count"] = len(retained)
    result["repair_intelligence"] = intelligence


def _canonicalize_summary(result: dict[str, Any]) -> None:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    score = maturity.get("score", result.get("technical_score"))
    level = maturity.get("level") or maturity.get("label") or "Unclassified"
    repository = result.get("repository") or "the authorized repository"
    result["executive_summary"] = f"NICO completed an authorized hosted Express Technical Health Assessment for {repository}. The canonical source maturity signal is {level} ({score}/100). The evidence-adjusted score is reported separately, and client delivery remains blocked pending exact-snapshot human review."


def normalize_express_decision_quality(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    _normalize_sections(output)
    _normalize_score_objects(output)
    _normalize_repair_candidates(output)
    _canonicalize_summary(output)
    output["express_decision_quality"] = {"status": "normalized", "version": VERSION, "language_false_positives_removed": True, "clean_evidence_excluded_from_findings": True, "clean_evidence_excluded_from_repair_priority": True, "cross_section_findings_deduplicated": True, "ci_counts_reconciled": True, "ci_categories_exactly_once": True, "score_bars_use_proportional_geometry": True, "scanner_worker_is_supplemental": True, "architecture_velocity_page_boundary": True, "unverified_secret_candidates_grouped": True, "unverified_executive_severity_gated": True, "canonical_summary_bound": True}
    return output


def _apply_normalized_result_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    existing_reports = result.get("reports")
    for key, value in normalized.items():
        if key == "reports" and isinstance(existing_reports, dict) and isinstance(value, dict):
            existing_reports.clear()
            existing_reports.update(value)
            result["reports"] = existing_reports
        else:
            result[key] = value


def _dossier_context(title: str) -> tuple[str, str, str, list[str]]:
    lower = title.casefold()
    file_match = re.search(r"([A-Za-z0-9_./-]+\.py)", title)
    file_path = file_match.group(1) if file_match else "the exact affected source files listed in the evidence ledger"
    metric_match = re.search(r"(?:score|loc|churn)=?[0-9.]+(?:,?\s*(?:score|loc|churn)=?[0-9.]+)*", title, re.I)
    metric = metric_match.group(0) if metric_match else "the retained complexity, churn, and ownership metrics"
    if "complexity" in lower or "hotspot" in lower or "high churn" in lower:
        return (f"Concentrated complexity and change activity in {file_path} increases regression probability, review time, and the cost of safely modifying the affected delivery path.", f"Assign an authorized owner to {file_path}; identify the highest-complexity functions and their callers; add characterization tests; then split one responsibility at a time while preserving public behavior and import compatibility.", f"Retain before/after {metric}; run focused tests for the affected module, the full suite, production build, import-order checks, and an immutable same-SHA rescan.", [f"Exact affected location: {file_path}.", f"Retained metric context: {metric}."])
    if "ownership concentration" in lower:
        return ("Concentrated ownership creates review bottlenecks and continuity risk when the primary maintainer is unavailable.", "Map the exact files and commit shares to responsible owners, add secondary reviewers for the highest-concentration paths, and document operational handoff for critical modules.", "Recompute ownership concentration from the same repository snapshot and confirm that critical paths have an accountable primary and secondary reviewer.", ["Use file-level ownership and commit-share evidence from the immutable evidence ledger."])
    if "failed" in lower or "timeout" in lower or "unavailable" in lower:
        return ("The analyzer result is incomplete, so release confidence is reduced; it does not independently establish a product defect.", "Restore the named analyzer with a bounded timeout and exact-snapshot command, retain stdout/stderr and exit disposition, and map any verified result to the relevant scored control.", "Rerun the exact analyzer on the immutable commit and require a terminal completed, inapplicable, or explicitly accepted review-limited disposition.", ["Analyzer lifecycle evidence must include command, status, exit result, snapshot SHA, and disposition."])
    return ("This review-limited record may affect engineering effort or release confidence, but material impact is not established until the exact location and evidence are confirmed.", "Confirm the exact location, rule or analyzer, immutable snapshot, and disposition before assigning repair work; do not fabricate a code change from generic evidence.", "Retain finding-specific evidence, run the focused verification appropriate to the confirmed location, and regenerate the assessment from the same immutable SHA.", ["Finding remains review-limited pending exact location and analyzer provenance."])


def _classify_dossier(dossier: Any) -> Any:
    title = _text(getattr(dossier, "title", ""))
    lower = title.casefold()
    severity = "review"
    if any(term in lower for term in ("verified vulnerability", "verified exposure", "confirmed vulnerability", "confirmed exposure")):
        severity = "high"
    elif any(term in lower for term in ("complexity", "hotspot", "high churn", "ownership concentration")):
        severity = "medium"
    if any(term in lower for term in _SIZE_ADVISORY_TERMS):
        severity = "informational"
    if any(term in lower for term in ("failed", "timeout", "timed out", "requires human review")):
        severity = "review"
    impact, repair_specification, verification, evidence = _dossier_context(title)
    useful = [item for item in list(getattr(dossier, "evidence", ()) or ()) if "repository root contains" not in _text(item).casefold()]
    updates = {"severity": severity, "confidence": "review-limited" if severity == "review" else getattr(dossier, "confidence", "review-limited"), "business_impact": impact, "repair_specification": repair_specification, "verification": verification, "owner": "Authorized engineering owner", "effort": getattr(dossier, "effort", "medium") or "medium", "disposition": "review_limited" if severity == "review" else getattr(dossier, "disposition", "open"), "evidence": tuple((useful + evidence)[:6])}
    if is_dataclass(dossier):
        try:
            return replace(dossier, **updates)
        except Exception:
            pass
    enriched = copy.copy(dossier)
    for key, value in updates.items():
        try:
            setattr(enriched, key, value)
        except Exception:
            return dossier
    return enriched


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
                title = getattr(dossier, "title", "")
                semantic = _key(title)
                if not semantic or semantic in seen or _is_language_false_positive(title) or _is_clean_evidence(title):
                    continue
                seen.add(semantic)
                output.append(_classify_dossier(dossier))
            return output
        setattr(classified_dossiers, _PATCH_MARKER, True)
        setattr(classified_dossiers, "_nico_previous", original_builder)
        dossier_export.build_finding_dossiers = classified_dossiers
        dossier_status = "installed"
    return {"status": "installed" if "installed" in {render_status, dossier_status} else "already_installed", "version": VERSION, "render_binding": render_status, "dossier_binding": dossier_status}


__all__ = ["VERSION", "_canonical_ci_categories", "_is_clean_evidence", "_is_language_false_positive", "_proportional_bar", "_reconcile_ci_statement", "install_express_decision_quality_v17", "normalize_express_decision_quality"]
