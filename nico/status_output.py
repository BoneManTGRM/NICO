from __future__ import annotations

from typing import Any

from nico.max_target_status import build_max_target_status


def attach_status_output(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    status = build_max_target_status(result)
    result["max_target_status"] = status
    result["max_target_summary"] = {
        "overall_score": status.get("overall_score"),
        "overall_target": status.get("overall_target"),
        "overall_gap": status.get("overall_gap"),
        "ready_for_all_max": status.get("ready_for_all_max"),
        "next_gate_count": len(status.get("next_gates") or []),
    }
    return result
