from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

REPORT_QUALITY_GATE_COMPAT_VERSION = "nico.report_quality_gate_compat.v1"
_PATCH_MARKER = "_nico_report_quality_gate_compat_v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _client_prose(payload: dict[str, Any], quality_module: Any) -> str:
    values: list[Any] = [payload.get("decision_summary"), payload.get("executive_summary")]
    decision = _dict(payload.get("decision_summary"))
    values.append(decision.get("recommended_actions"))
    values.append(payload.get("next_steps"))
    for section in _list(payload.get("sections")):
        if not isinstance(section, dict):
            continue
        # Scanner evidence may legitimately contain TODO/TBD strings from the
        # assessed repository. Only presentation prose is placeholder-gated.
        values.extend([section.get("label"), section.get("summary")])
    return quality_module._text(values)


def _recompute(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    issues = [item for item in _list(output.get("issues")) if isinstance(item, dict)]
    critical = [item for item in issues if item.get("severity") == "critical"]
    warnings = [item for item in issues if item.get("severity") == "warning"]
    quality_score = max(0, min(100, 100 - len(critical) * 24 - len(warnings) * 4))
    output["issues"] = issues
    output["critical_issue_count"] = len(critical)
    output["warning_count"] = len(warnings)
    output["quality_score"] = quality_score
    output["status"] = "blocked" if critical else "ready_for_human_review" if quality_score >= 84 else "review_required"
    return output


def install_report_quality_gate_compat() -> dict[str, Any]:
    from nico import report_quality_gate as quality

    current: Callable[[dict[str, Any], str], dict[str, Any]] = quality.evaluate_report_payload
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": REPORT_QUALITY_GATE_COMPAT_VERSION}

    @wraps(current)
    def compatible(payload: dict[str, Any], tier: str) -> dict[str, Any]:
        normalized_tier = str(tier or "unknown").lower()
        result = current(payload, tier)
        issues = [deepcopy(item) for item in _list(result.get("issues")) if isinstance(item, dict)]

        if normalized_tier == "full":
            for issue in issues:
                if issue.get("code") == "missing_snapshot_identity" and issue.get("severity") == "critical":
                    issue["severity"] = "warning"
                    issue["message"] = (
                        "The Full report is not bound to an exact commit snapshot. It must remain review-limited and disclose the available repository/source scope."
                    )

        prose = _client_prose(payload, quality)
        if not quality._PLACEHOLDER_RE.search(prose):
            issues = [item for item in issues if item.get("code") != "placeholder_content"]

        adjusted = deepcopy(result)
        adjusted["issues"] = issues
        adjusted.setdefault("checks", {})["placeholder_scope"] = "client_presentation_prose_only"
        adjusted["checks"]["full_missing_snapshot_policy"] = "warning_and_review_limited"
        return _recompute(adjusted)

    setattr(compatible, _PATCH_MARKER, True)
    setattr(compatible, "_nico_previous", current)
    quality.evaluate_report_payload = compatible
    return {
        "status": "installed",
        "version": REPORT_QUALITY_GATE_COMPAT_VERSION,
        "full_missing_snapshot_review_limited": True,
        "repository_evidence_placeholder_false_positive_prevented": True,
        "client_presentation_placeholders_blocked": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "REPORT_QUALITY_GATE_COMPAT_VERSION",
    "install_report_quality_gate_compat",
]
