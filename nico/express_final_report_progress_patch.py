from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_final_report_progress.v1"
_MARKER = "_nico_express_final_report_progress_v1"


def _replace(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace(
            "Draft report artifacts are ready for required human review",
            "Final report artifacts are ready for required human review",
        ).replace(
            "draft report artifacts are ready for human review",
            "final report artifacts are ready for required human review",
        )
    if isinstance(value, list):
        return [_replace(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item) for key, item in value.items()}
    return value


def install_express_final_report_progress_patch() -> dict[str, Any]:
    from nico import express_async_api

    express_async_api._EXPRESS_STAGE_DEFINITIONS = tuple(
        (
            step,
            "Assessment completed and final report artifacts are ready for required human review."
            if step == "complete"
            else _replace(label),
        )
        for step, label in express_async_api._EXPRESS_STAGE_DEFINITIONS
    )
    current: Callable[..., Any] = express_async_api._stage_progress
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def stage_progress(*args: Any, **kwargs: Any) -> Any:
        return _replace(current(*args, **kwargs))

    setattr(stage_progress, _MARKER, True)
    setattr(stage_progress, "_nico_previous", current)
    express_async_api._stage_progress = stage_progress
    return {
        "status": "installed",
        "version": VERSION,
        "draft_progress_copy_present": False,
        "final_report_pending_human_review": True,
    }


__all__ = ["VERSION", "install_express_final_report_progress_patch"]
