from __future__ import annotations

from typing import Any

from nico.report_evidence_consistency_gate import (
    COMPLEXITY_LINE_FRAGMENTS,
    _apply_complexity_gate,
    _dict,
    _list,
    _recompute_maturity,
    _reconcile_secret_history,
)


def _complexity_signal_present(result: dict[str, Any]) -> bool:
    """Return true only when the report actually contains complexity proof or claims."""

    if _dict(result.get("complexity_artifact")):
        return True
    if _dict(result.get("complexity_engine")):
        return True
    if _dict(result.get("complexity_engine_summary")):
        return True
    scanner = _dict(result.get("scanner_worker_artifact"))
    if _dict(scanner.get("complexity_engine")) or _dict(scanner.get("complexity_engine_summary")):
        return True

    fragments = tuple(fragment.lower() for fragment in COMPLEXITY_LINE_FRAGMENTS)
    for section in _list(result.get("sections")):
        if not isinstance(section, dict):
            continue
        if section.get("id") not in {"velocity_complexity", "architecture_debt"}:
            continue
        values: list[Any] = [section.get("summary")]
        values.extend(_list(section.get("evidence")))
        values.extend(_list(section.get("findings")))
        values.extend(_list(section.get("unavailable")))
        if any(fragment in str(value or "").lower() for fragment in fragments for value in values):
            return True
        score_lift = _dict(section.get("scanner_score_lift"))
        if score_lift.get("applied") is True:
            return True
    return False


def apply_report_evidence_consistency_gate(result: dict[str, Any]) -> dict[str, Any]:
    """Apply cross-tier consistency only where the report contains relevant evidence."""

    if result.get("status") != "complete":
        return result
    complexity_changed = False
    if _complexity_signal_present(result):
        complexity_changed = _apply_complexity_gate(result)
    _reconcile_secret_history(result)
    if complexity_changed:
        _recompute_maturity(result)
    return result


__all__ = ["apply_report_evidence_consistency_gate"]
