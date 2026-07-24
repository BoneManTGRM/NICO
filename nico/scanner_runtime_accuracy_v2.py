from __future__ import annotations

from dataclasses import replace
from typing import Any

VERSION = "nico.scanner_runtime_accuracy.v2"


def install_scanner_runtime_accuracy_v2() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners
    from nico import scanner_worker_orchestration as orchestration

    updated: list[str] = []
    next_specs = []
    for spec in runners.TOOL_SPECS:
        command = spec.command
        timeout_seconds = spec.timeout_seconds
        max_output_chars = spec.max_output_chars
        if spec.name == "eslint":
            command = ("eslint", ".", "--format", "json")
            timeout_seconds = max(timeout_seconds, 240)
        elif spec.name == "semgrep":
            timeout_seconds = max(timeout_seconds, 360)
        elif spec.name in {"gitleaks", "trufflehog"}:
            timeout_seconds = max(timeout_seconds, 600)
            max_output_chars = max(max_output_chars, 120_000)
        next_spec = replace(
            spec,
            command=command,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )
        next_specs.append(next_spec)
        if next_spec != spec:
            updated.append(spec.name)

    specs = tuple(next_specs)
    runners.TOOL_SPECS = specs
    orchestration.TOOL_SPECS = specs
    defaults = runners.run_scanner_tools.__defaults__
    if defaults:
        runners.run_scanner_tools.__defaults__ = (specs, *defaults[1:])

    return {
        "status": "installed",
        "version": VERSION,
        "updated_tools": updated,
        "eslint_uses_installed_binary": True,
        "eslint_requires_real_configuration": True,
        "typescript_remains_distinct": True,
        "history_scan_scope_preserved": True,
        "history_tool_timeout_seconds": 600,
        "semgrep_timeout_seconds": 360,
        "missing_or_failed_tools_remain_non_clean": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_scanner_runtime_accuracy_v2"]
