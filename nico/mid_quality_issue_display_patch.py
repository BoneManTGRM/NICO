from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_QUALITY_ISSUE_DISPLAY_VERSION = "nico.mid_quality_issue_display.v1"
_MARKER = "_nico_mid_quality_issue_display_v1"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _issue_label(issue: dict[str, Any]) -> str:
    code = _bounded(issue.get("code") or "unknown_quality_check", 80)
    section_id = _bounded(issue.get("section_id"), 80)
    return f"{code} ({section_id})" if section_id else code


def apply_mid_quality_issue_display(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    if str(output.get("report_generation_status") or "").lower() != "blocked":
        output["mid_quality_issue_display_version"] = MID_QUALITY_ISSUE_DISPLAY_VERSION
        return output

    issues = [item for item in _list(output.get("report_quality_issues")) if isinstance(item, dict)]
    critical = [item for item in issues if str(item.get("severity") or "").lower() == "critical"]
    if not critical:
        output["mid_quality_issue_display_version"] = MID_QUALITY_ISSUE_DISPLAY_VERSION
        return output

    labels: list[str] = []
    details: list[dict[str, str]] = []
    for issue in critical:
        label = _issue_label(issue)
        if label not in labels:
            labels.append(label)
        details.append(
            {
                "code": _bounded(issue.get("code"), 80),
                "section_id": _bounded(issue.get("section_id"), 80),
                "message": _bounded(issue.get("message"), 220),
                "label": label,
            }
        )

    message = (
        f"Mid draft blocked by {len(critical)} critical report-quality check(s): "
        + "; ".join(labels)
        + "."
    )
    output["report_quality_blockers"] = labels
    output["report_quality_blocker_details"] = details
    output["report_generation_error"] = message
    output["report_generation_note"] = message

    progress = [deepcopy(item) for item in _list(output.get("progress")) if isinstance(item, dict)]
    for item in progress:
        if str(item.get("step") or "") != "reports":
            continue
        item["message"] = message
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        evidence["critical_issue_labels"] = labels
        evidence["critical_issue_details"] = details
        item["evidence"] = evidence
    output["progress"] = progress
    output["mid_quality_issue_display_version"] = MID_QUALITY_ISSUE_DISPLAY_VERSION
    return output


def install_mid_quality_issue_display_patch() -> dict[str, Any]:
    from nico import mid_terminal_truth_patch as terminal

    current: Callable[[dict[str, Any]], dict[str, Any]] = terminal.normalize_mid_terminal_truth
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": MID_QUALITY_ISSUE_DISPLAY_VERSION}

    @wraps(current)
    def normalize_with_issue_labels(result: dict[str, Any]) -> dict[str, Any]:
        return apply_mid_quality_issue_display(current(result))

    setattr(normalize_with_issue_labels, _MARKER, True)
    setattr(normalize_with_issue_labels, "_nico_previous", current)
    terminal.normalize_mid_terminal_truth = normalize_with_issue_labels
    return {
        "status": "installed",
        "version": MID_QUALITY_ISSUE_DISPLAY_VERSION,
        "duplicate_codes_deduplicated_for_display": True,
        "section_ids_exposed": True,
        "quality_gate_weakened": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_QUALITY_ISSUE_DISPLAY_VERSION",
    "apply_mid_quality_issue_display",
    "install_mid_quality_issue_display_patch",
]
