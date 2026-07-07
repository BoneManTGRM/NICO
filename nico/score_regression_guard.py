from __future__ import annotations

from typing import Any

SCORE_PATHS = {
    "technical_maturity": ("maturity_signal", "score"),
    "max_target_readiness": ("max_target_status", "overall_score"),
    "max_target_summary": ("max_target_summary", "overall_score"),
}


def _score(payload: dict[str, Any], path: tuple[str, str]) -> int | None:
    value: Any = payload or {}
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_score_regression_guard(previous: dict[str, Any], current: dict[str, Any], tolerance: int = 1) -> dict[str, Any]:
    rows = []
    regressions = []
    for label, path in SCORE_PATHS.items():
        before = _score(previous or {}, path)
        after = _score(current or {}, path)
        if before is None or after is None:
            delta = None
            state = "unavailable"
        else:
            delta = after - before
            if delta < -abs(tolerance):
                state = "regression_review_required"
                regressions.append(label)
            elif delta > abs(tolerance):
                state = "improved"
            else:
                state = "stable"
        rows.append({"score": label, "previous": before, "current": after, "delta": delta, "state": state})
    return {
        "status": "regression_review_required" if regressions else "ok",
        "tolerance": abs(tolerance),
        "regressions": regressions,
        "scores": rows,
        "rule": "A score drop beyond tolerance must be explained before delivery. Technical maturity and max-target readiness are tracked separately so stricter readiness gates do not look like code-quality regression.",
        "next_actions": [
            "Confirm whether the displayed number is technical maturity or max-target readiness.",
            "If only readiness dropped, complete missing evidence gates instead of lowering the technical maturity claim.",
            "If technical maturity dropped, inspect section-level score changes and evidence-source availability before delivery.",
        ] if regressions else [],
    }
