from __future__ import annotations

import re
from typing import Any, Callable

PATCH_VERSION = "nico.client_output_truth_sanitization.v1"
_FRIENDLY_MARKER = "_nico_client_output_truth_friendly_v1"
_RECONCILE_MARKER = "_nico_client_output_truth_reconcile_v1"
_ACTION_MARKER = "_nico_client_output_truth_actions_v1"

_NONE_METRIC_PATTERN = re.compile(
    r"\b(max_function_cyclomatic|density|function_cyclomatic|cyclomatic_density|coverage_ratio)=None\b",
    flags=re.IGNORECASE,
)
_STALE_GREEN_CI_ACTION_MARKERS = (
    "add one green ci run",
    "add a green ci run",
    "create one green ci run",
    "create a green ci run",
    "establish one green ci run",
    "establish a green ci run",
)


def sanitize_client_text(value: Any) -> str:
    text = str(value or "")
    return _NONE_METRIC_PATTERN.sub(lambda match: f"{match.group(1)}=unavailable", text)


def _sanitize_section_text(finalized: dict[str, Any]) -> None:
    for section in finalized.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        if "summary" in section:
            section["summary"] = sanitize_client_text(section.get("summary"))
        for key in ("evidence", "findings", "unavailable"):
            section[key] = [
                sanitize_client_text(item)
                for item in section.get(key, []) or []
                if str(item).strip()
            ]
    for key in (
        "executive_summary",
        "resourcing_recommendation",
        "risk_register",
        "verification_checklist",
        "medium_term_plan",
        "quick_wins",
    ):
        value = finalized.get(key)
        if isinstance(value, list):
            finalized[key] = [sanitize_client_text(item) for item in value if str(item).strip()]
        elif isinstance(value, str):
            finalized[key] = sanitize_client_text(value)


def _ci_is_verified_green(finalized: dict[str, Any]) -> bool:
    section = next(
        (
            item
            for item in finalized.get("sections", []) or []
            if isinstance(item, dict) and str(item.get("id") or "") == "ci_cd"
        ),
        None,
    )
    if not section:
        return False
    try:
        score = int(section.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    findings = " ".join(str(item) for item in section.get("findings", []) or []).lower()
    current_failure = any(
        marker in findings
        for marker in (
            "no ci/cd workflow",
            "no github actions workflow",
            "current workflow failed",
            "current ci failed",
            "required checks are failing",
        )
    )
    return str(section.get("status") or "").lower() == "green" and score >= 90 and not current_failure


def install_client_output_truth_sanitization() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_completion_score_binding as completion

    friendly_status = "already_installed"
    current_friendly = assessment_quality._friendly_note
    if not getattr(current_friendly, _FRIENDLY_MARKER, False):
        original_friendly: Callable[[Any], str] = current_friendly

        def friendly_note_with_truth(value: Any) -> str:
            return sanitize_client_text(original_friendly(value))

        setattr(friendly_note_with_truth, _FRIENDLY_MARKER, True)
        setattr(friendly_note_with_truth, "_nico_previous", original_friendly)
        assessment_quality._friendly_note = friendly_note_with_truth
        friendly_status = "installed"

    reconcile_status = "already_installed"
    current_reconcile = completion._reconcile_final_section_truth
    if not getattr(current_reconcile, _RECONCILE_MARKER, False):
        original_reconcile: Callable[[dict[str, Any]], None] = current_reconcile

        def reconcile_with_client_truth(finalized: dict[str, Any]) -> None:
            original_reconcile(finalized)
            _sanitize_section_text(finalized)

        setattr(reconcile_with_client_truth, _RECONCILE_MARKER, True)
        setattr(reconcile_with_client_truth, "_nico_previous", original_reconcile)
        completion._reconcile_final_section_truth = reconcile_with_client_truth
        reconcile_status = "installed"

    action_status = "already_installed"
    current_actions = completion._refresh_client_actions
    if not getattr(current_actions, _ACTION_MARKER, False):
        original_actions: Callable[[dict[str, Any], dict[str, Any]], None] = current_actions

        def refresh_actions_with_ci_truth(finalized: dict[str, Any], final_repairs: dict[str, Any]) -> None:
            original_actions(finalized, final_repairs)
            ci_green = _ci_is_verified_green(finalized)
            if ci_green:
                finalized["quick_wins"] = [
                    item
                    for item in finalized.get("quick_wins", []) or []
                    if not any(marker in str(item).lower() for marker in _STALE_GREEN_CI_ACTION_MARKERS)
                ]
            summary = finalized.get("repair_action_summary")
            if isinstance(summary, dict):
                summary["ci_quick_win_suppressed_because_ci_verified_green"] = ci_green
            _sanitize_section_text(finalized)

        setattr(refresh_actions_with_ci_truth, _ACTION_MARKER, True)
        setattr(refresh_actions_with_ci_truth, "_nico_previous", original_actions)
        completion._refresh_client_actions = refresh_actions_with_ci_truth
        action_status = "installed"

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "friendly_note": friendly_status,
        "final_section_reconciliation": reconcile_status,
        "client_actions": action_status,
        "none_metrics_rendered_as_unavailable": True,
        "verified_green_ci_action_suppression": True,
        "report_only": True,
        "automatic_application_allowed": False,
    }


__all__ = [
    "PATCH_VERSION",
    "install_client_output_truth_sanitization",
    "sanitize_client_text",
]
