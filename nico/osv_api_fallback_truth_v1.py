from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico import scanner_tool_runners


VERSION = "nico.osv_api_fallback_truth.v1"
_MARKER = "_nico_osv_api_fallback_truth_v1"


def _is_osv_api_fallback(spec: Any, result: dict[str, Any]) -> bool:
    tool_name = str(getattr(spec, "name", "") or result.get("tool") or "").casefold()
    fallback = str(result.get("fallback") or "").casefold()
    command_intent = str(result.get("command_intent") or "").casefold()
    return bool(
        tool_name == "osv-scanner"
        and result.get("status") == "completed"
        and (
            fallback == "osv querybatch api"
            or command_intent == "osv-api querybatch"
        )
    )


def install_osv_api_fallback_truth_v1() -> dict[str, Any]:
    """Make the verified OSV API fallback source explicit after all scanner wrappers.

    NICO may use the OSV querybatch API when the pinned osv-scanner CLI is not
    available. That is real current-run dependency evidence, but it must never be
    mislabeled as CLI execution. Compatibility installers can replace the public
    scanner function, so this binding is intentionally re-entrant and installed at
    the final package boundary.
    """

    current: Callable[..., Any] = scanner_tool_runners.run_scanner_tool
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "execution_source": "osv_api_fallback",
            "cli_execution_claimed": False,
            "current_run_evidence": True,
        }

    @wraps(current)
    def run_scanner_tool_with_osv_source(
        spec: Any,
        workspace: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = current(spec, workspace, *args, **kwargs)
        if not isinstance(result, dict) or not _is_osv_api_fallback(spec, result):
            return result
        output = dict(result)
        output["execution_source"] = "osv_api_fallback"
        output.setdefault("current_run", True)
        output.setdefault("verified_for_this_report", True)
        output.setdefault(
            "source_disclosure",
            "The pinned osv-scanner CLI was unavailable; NICO queried the OSV querybatch API for exact dependency versions in this run.",
        )
        return output

    setattr(run_scanner_tool_with_osv_source, _MARKER, True)
    setattr(run_scanner_tool_with_osv_source, "_nico_previous", current)
    scanner_tool_runners.run_scanner_tool = run_scanner_tool_with_osv_source

    # The snapshot worker imports the scanner module as an alias. Reassert the
    # public binding explicitly so later import order cannot hide the source field.
    try:
        from nico import snapshot_scanner_worker

        snapshot_scanner_worker.tool_runners.run_scanner_tool = (
            run_scanner_tool_with_osv_source
        )
    except Exception:
        pass

    return {
        "status": "installed",
        "version": VERSION,
        "execution_source": "osv_api_fallback",
        "cli_execution_claimed": False,
        "current_run_evidence": True,
    }


__all__ = ["VERSION", "install_osv_api_fallback_truth_v1"]
