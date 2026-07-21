from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_terminal_runtime_boundary.v37"
_PATCH_MARKER = "_nico_express_terminal_runtime_boundary_v37"
_STATUS_SCORE_RE = re.compile(r"\b(GREEN|YELLOW|RED)\s+(\d{1,3})(?!\s*/\s*100)", re.I)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _merge(*groups: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in _list(group):
            item = str(value or "").strip()
            key = " ".join(item.split()).casefold()
            if item and key not in seen:
                seen.add(key)
                output.append(item)
    return output


def _sanitize_string(value: str) -> str:
    return _STATUS_SCORE_RE.sub(lambda match: f"{match.group(2)}/100 {match.group(1).upper()}", value)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    return value


def _ensure_legacy_presented_fields(result: dict[str, Any]) -> tuple[list[Any], int]:
    from nico.express_terminal_report_truth_v34 import normalize_section_aliases

    normalize_section_aliases(result)
    scores: list[int] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        not_scored = section_id in {"scanner_worker", "scanner_worker_evidence"} or (
            section_id in {"client_acceptance", "client_human_acceptance"}
            and _text(section.get("status")).casefold() not in {"approved", "accepted", "green"}
        )
        if not_scored:
            continue
        raw = section.get("score")
        if not isinstance(raw, (int, float)):
            continue
        score = int(raw)
        section["source_score"] = score
        section["presented_score"] = score
        section["presented_status"] = _text(section.get("status") or "unknown").casefold()
        section["presented_confidence"] = section.get("confidence") or "standard"
        section["directly_scored"] = True
        section["score_deductions"] = []
        section["score_rationale"] = "Existing canonical trust score preserved; no second deduction pass was applied."
        scores.append(score)
    overall = round(sum(scores) / len(scores)) if scores else 0
    result["evidence_adjusted_score"] = overall
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    if isinstance(maturity, dict):
        maturity["source_score"] = maturity.get("score")
        maturity["presented_score"] = overall
        maturity["score_treatment"] = "canonical_legacy_trust_scores_preserved_without_double_deduction"
    return [], overall


def _append_service_guidance(markdown: str, result: dict[str, Any]) -> str:
    selected: list[str] = []
    for value in [*result.get("quick_wins", []), *result.get("medium_term_plan", [])]:
        item = str(value or "").strip()
        lowered = item.casefold()
        if item and any(term in lowered for term in ("next service tier", "one-click mid technical health assessment", "as easy as express")):
            selected.append(item)
    selected = _merge(selected)
    missing = [item for item in selected if item not in markdown]
    if not missing:
        return markdown
    lines = [markdown.rstrip(), "", "## Service Continuity and Upgrade Path", *[f"- {item}" for item in missing], ""]
    return "\n".join(lines)


def install_express_terminal_runtime_boundary_v37() -> dict[str, Any]:
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import express_report_premium_v14 as premium
    from nico import express_scanner_disposition_truth_v1 as scanner
    from nico import express_terminal_report_compat_v36 as compat
    from nico import hosted_truth_delivery_gate as hosted_gate
    from nico.hosted_assessment import build_html

    if getattr(scoring.reconcile_express_scores, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    previous_scanner = scanner.reconcile_express_scanner_dispositions
    previous_scoring = scoring.reconcile_express_scores
    previous_gate = hosted_gate.apply_final_hosted_truth_gate

    @wraps(previous_scanner)
    def gated_scanner(result: dict[str, Any]) -> dict[str, Any]:
        if compat._has_authoritative_current_run_evidence(result):
            return previous_scanner(result)
        return result

    @wraps(previous_scoring)
    def gated_scoring(result: dict[str, Any]) -> tuple[list[Any], int]:
        if compat._has_authoritative_current_run_evidence(result):
            return previous_scoring(result)
        return _ensure_legacy_presented_fields(result)

    @wraps(previous_gate)
    def final_gate(result: dict[str, Any]) -> dict[str, Any]:
        existing = {
            key: list(result.get(key) or [])
            for key in ("priority_actions", "quick_wins", "medium_term_plan", "resourcing_recommendation", "risk_register", "verification_checklist")
        }
        output = previous_gate(result)
        for key, values in existing.items():
            output[key] = _merge(values, output.get(key))
        sanitized = _sanitize_value(output)
        if isinstance(sanitized, dict):
            output = sanitized
        reports = output.get("reports") if isinstance(output.get("reports"), dict) else {}
        markdown = reports.get("markdown")
        if isinstance(markdown, str):
            markdown = _sanitize_string(markdown)
            markdown = _append_service_guidance(markdown, output)
            reports["markdown"] = markdown
            reports["html"] = build_html(markdown)
            output["reports"] = reports
        output["express_terminal_runtime_boundary"] = {
            "status": "complete",
            "version": VERSION,
            "authoritative_current_run_scoring": compat._has_authoritative_current_run_evidence(output),
            "legacy_double_deduction_blocked": True,
            "final_export_sanitized_after_all_truth_gates": True,
            "service_tier_guidance_preserved": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return output

    for function, previous in (
        (gated_scanner, previous_scanner),
        (gated_scoring, previous_scoring),
        (final_gate, previous_gate),
    ):
        setattr(function, _PATCH_MARKER, True)
        setattr(function, "_nico_previous", previous)

    scanner.reconcile_express_scanner_dispositions = gated_scanner
    scoring.reconcile_express_scores = gated_scoring
    premium.reconcile_express_scores = gated_scoring
    hosted_gate.apply_final_hosted_truth_gate = final_gate
    return {
        "status": "installed",
        "version": VERSION,
        "scanner_truth_gated_to_authoritative_current_run": True,
        "evidence_specific_scoring_gated_to_authoritative_current_run": True,
        "legacy_truth_scores_preserved": True,
        "final_export_sanitization": True,
        "service_tier_guidance_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_terminal_runtime_boundary_v37"]
