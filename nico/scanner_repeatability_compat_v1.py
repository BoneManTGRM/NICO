from __future__ import annotations

from functools import wraps
from threading import RLock
from typing import Any, Callable

from nico import scanner_tool_runners as runners

VERSION = "nico.scanner_repeatability_compat.v1"
_MARKER = "_nico_scanner_repeatability_compat_v1"
_PARSE_LOCK = RLock()


def _finding_list(value: Any) -> list[Any]:
    if isinstance(value, tuple) and len(value) == 3 and isinstance(value[0], list):
        return value[0]
    return value if isinstance(value, list) else []


def _verified_current_run_unavailable(payload: dict[str, Any]) -> dict[str, Any]:
    output = dict(payload)
    status = str(output.get("status") or "").casefold()
    reason = str(output.get("reason") or output.get("failure_or_unavailable_reason") or "").casefold()
    directly_verified_absence = status == "unavailable" and any(
        token in reason
        for token in (
            "not installed in the worker image",
            "is not installed",
            "not found for",
            "no matching files",
        )
    )
    if directly_verified_absence and "project commands" not in reason and "disabled" not in reason:
        output["current_run"] = True
        output["verified_for_this_report"] = True
        output["clean_result_verified"] = False
        output["verified_fact"] = "The tool was verified unavailable for this exact current run; no clean-code claim is made."
    return output


def install_scanner_repeatability_compat_v1() -> dict[str, Any]:
    current_tool: Callable[..., dict[str, Any]] = runners.run_scanner_tool
    if bool(getattr(current_tool, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "public_parser_returns_findings_list": True,
            "complete_capture_metadata_retained": True,
            "legacy_tool_wrappers_accept_preparation": True,
            "verified_unavailability_is_not_clean_evidence": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    complete_parser: Callable[..., Any] = runners.parse_tool_findings

    @wraps(complete_parser)
    def public_parser(tool_name: str, result: Any) -> list[Any]:
        return _finding_list(complete_parser(tool_name, result))

    # Older hosted execution layers imported the public parser by value. Keep their
    # stable list-returning API while the native runner retains complete-capture metadata.
    for module_name in (
        "hosted_dependency_scanner_execution_patch",
        "hosted_static_scanner_execution_patch",
        "hosted_secret_scanner_execution_patch",
        "scanner_score_lift_execution",
        "scanner_output_truth_patch",
        "secret_history_scan",
    ):
        try:
            module = __import__(f"nico.{module_name}", fromlist=[module_name])
        except Exception:
            continue
        if hasattr(module, "parse_tool_findings"):
            setattr(module, "parse_tool_findings", public_parser)

    runners.parse_tool_findings = public_parser

    @wraps(current_tool)
    def compatible_tool(
        spec: Any,
        workspace: Any,
        *,
        runner: Any = runners.run_command,
        preparation: Any = None,
    ) -> dict[str, Any]:
        # The native complete-output runner expects its private tuple parser, while
        # legacy wrappers expect the public list parser. Switch only around the bounded
        # call and serialize the swap so concurrent scanner runs cannot observe it.
        del preparation  # npm preparation has already populated the exact workspace.
        with _PARSE_LOCK:
            runners.parse_tool_findings = complete_parser
            try:
                payload = current_tool(spec, workspace, runner=runner)
            finally:
                runners.parse_tool_findings = public_parser
        return _verified_current_run_unavailable(payload) if isinstance(payload, dict) else payload

    setattr(compatible_tool, _MARKER, True)
    setattr(compatible_tool, "_nico_previous", current_tool)
    runners.run_scanner_tool = compatible_tool
    return {
        "status": "installed",
        "version": VERSION,
        "public_parser_returns_findings_list": True,
        "complete_capture_metadata_retained": True,
        "legacy_tool_wrappers_accept_preparation": True,
        "verified_unavailability_is_not_clean_evidence": True,
        "automatic_clean_claim_from_unavailable_tool": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_scanner_repeatability_compat_v1"]
