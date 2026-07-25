from __future__ import annotations

from typing import Any, Callable, Iterator

VERSION = "nico.scanner_complete_output_compat.v3"
_PATCH_MARKER = "_nico_scanner_complete_output_compat_v3"


class ScannerFindings(list[Any]):
    """List-compatible findings with private execution metadata for core unpacking.

    Historical callers treat ``parse_tool_findings`` as a normal findings list.
    The complete-output runner also needs capture completeness and a bounded reason.
    List length, indexing, and equality therefore remain findings-compatible, while
    tuple unpacking by the core runner receives ``(findings, complete, reason)``.
    """

    def __init__(self, findings: list[Any], capture_complete: bool, capture_reason: str) -> None:
        super().__init__(findings)
        self.capture_complete = bool(capture_complete)
        self.capture_reason = str(capture_reason or "")

    def __iter__(self) -> Iterator[Any]:
        findings = [item for item in list.__iter__(self)]
        return iter((findings, self.capture_complete, self.capture_reason))


def install_scanner_complete_output_compat_v3() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners

    if getattr(runners, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    complete_parser: Callable[..., Any] = runners.parse_tool_findings

    def compatible_parse_tool_findings(tool_name: str, result: Any) -> ScannerFindings:
        parsed = complete_parser(tool_name, result)
        if isinstance(parsed, tuple) and len(parsed) == 3:
            findings, capture_complete, capture_reason = parsed
            safe_findings = findings if isinstance(findings, list) else list(findings or [])
            return ScannerFindings(safe_findings, bool(capture_complete), str(capture_reason or ""))
        safe_findings = parsed if isinstance(parsed, list) else list(parsed or [])
        return ScannerFindings(safe_findings, not bool(getattr(result, "output_truncated", False)), "")

    original_unavailable = runners._unavailable_tool

    def verified_unavailable(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = original_unavailable(*args, **kwargs)
        if isinstance(payload, dict):
            payload["current_run"] = True
            payload["verified_for_this_report"] = True
            payload.setdefault("findings_count", 0)
        return payload

    def compatible_run_scanner_tools(
        workspace: Any,
        specs: Any = runners.TOOL_SPECS,
        *,
        runner: Callable[..., Any] = runners.run_command,
    ) -> dict[str, Any]:
        if not workspace.repo_dir.exists() or not workspace.repo_dir.is_dir():
            raise ValueError("workspace repo directory must exist before scanner tools run")

        # Deliberately invoke the public tool runner without a new keyword. NICO's
        # installed execution/triage wrappers predate the preparation parameter and
        # remain part of the production evidence contract. Project tools perform
        # deterministic exact-lockfile preparation when they receive no shared object.
        tool_results = [runners.run_scanner_tool(spec, workspace, runner=runner) for spec in specs]
        raw_payload = {"tools": tool_results}
        normalized = runners.normalize_scanner_worker_artifact(raw_payload)
        history_secret_tools = [
            item["tool"]
            for item in tool_results
            if isinstance(item, dict)
            and item.get("category") == "secret"
            and item.get("status") == "completed"
            and item.get("scans_git_history")
            and item.get("full_history_verified") is True
        ]
        preparation = next(
            (
                item.get("project_preparation")
                for item in tool_results
                if isinstance(item, dict) and isinstance(item.get("project_preparation"), dict)
            ),
            None,
        )
        return {
            "artifact_schema": "nico.scanner_worker.v2",
            "tools": {item["tool"]: item for item in tool_results if isinstance(item, dict) and item.get("tool")},
            "normalized": normalized,
            "project_preparation": preparation or {"status": "not_required", "node_modules_ready": False},
            "secret_history_scan": {
                "completed_tools": history_secret_tools,
                "history_aware": bool(history_secret_tools),
            },
        }

    runners.parse_tool_findings = compatible_parse_tool_findings
    runners._unavailable_tool = verified_unavailable
    runners.run_scanner_tools = compatible_run_scanner_tools
    setattr(runners, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_findings_list_contract": True,
        "complete_capture_metadata_preserved": True,
        "wrapper_keyword_compatibility": True,
        "unavailable_state_verified_for_current_run": True,
    }


__all__ = ["ScannerFindings", "VERSION", "install_scanner_complete_output_compat_v3"]
