from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_failure_diagnostics.v1"
_MARKER = "_nico_comprehensive_failure_diagnostics_v1"


def install_comprehensive_failure_diagnostics_v1() -> dict[str, Any]:
    from nico import comprehensive_api_controller as controller

    current: Callable[[str, Any], dict[str, Any]] = controller._project_stage_result
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def project(stage_id: str, result: Any) -> dict[str, Any]:
        output = current(stage_id, result)
        if not isinstance(result, dict):
            return output
        for key in (
            "failed_checks",
            "final_artifact_truth",
            "score_recalculation",
            "checks",
        ):
            if key in result:
                output[key] = controller._bounded_value(result[key])
        evidence = result.get("evidence")
        if isinstance(evidence, dict):
            for key in ("failed_checks", "score_recalculation"):
                if key in evidence and key not in output:
                    output[key] = controller._bounded_value(evidence[key])
        return output

    setattr(project, _MARKER, True)
    setattr(project, "_nico_previous", current)
    controller._project_stage_result = project
    return {
        "status": "installed",
        "version": VERSION,
        "bound": controller._project_stage_result is project,
        "failed_checks_visible": True,
        "score_recalculation_visible": True,
        "large_artifacts_remain_bounded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_failure_diagnostics_v1"]
