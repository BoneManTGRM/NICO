from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import nico.snapshot_assessment_handlers as snapshot_handlers
import nico.snapshot_scanner_worker as snapshot_worker


TOOL_POLICY_VERSION = "nico-required-assessment-tools-v3"
REQUIRED_DEPENDENCY_TOOL = "osv-scanner"
REQUIRED_EXACT_SNAPSHOT_TOOLS: tuple[str, ...] = (
    # Collect fast current-tree evidence first so full-history work cannot consume
    # the entire bounded run before dependency and static coverage is attempted.
    "nico-secrets",
    "nico-static",
    "bandit",
    "semgrep",
    REQUIRED_DEPENDENCY_TOOL,
    # Full-history scanners are intentionally last and independently disclose
    # timeout, shallow history, CLI failure, and findings.
    "gitleaks",
    "trufflehog",
)

_ORIGINAL_START_SNAPSHOT_SCAN: Callable[[dict[str, Any]], dict[str, Any]] = snapshot_worker.start_snapshot_scan


def complete_assessment_tools(requested: Any) -> list[str]:
    """Return a stable, de-duplicated tool request with mandatory evidence tools.

    Browser clients may carry an older explicit tool list. An explicit list previously
    caused ``scanner_worker.selected_tools`` to omit every newly added scanner. This
    function keeps caller-selected optional tools while ensuring the exact-snapshot
    evidence needed by current scoring is requested on every authorized assessment.

    Current-tree and dependency analyzers are ordered before full-history scanners.
    That ordering does not weaken history requirements; it prevents a long history
    fetch or scan from starving every later evidence category under the total timeout.
    """

    values = requested if isinstance(requested, list) else []
    normalized = [str(item).strip() for item in values if str(item).strip()]
    return list(dict.fromkeys([*REQUIRED_EXACT_SNAPSHOT_TOOLS, *normalized]))


def start_snapshot_scan_with_required_tools(payload: dict[str, Any]) -> dict[str, Any]:
    request = deepcopy(payload)
    original = request.get("tools") if isinstance(request.get("tools"), list) else []
    request["tools"] = complete_assessment_tools(original)
    result = _ORIGINAL_START_SNAPSHOT_SCAN(request)
    if isinstance(result, dict):
        result = deepcopy(result)
        result["tool_policy"] = {
            "version": TOOL_POLICY_VERSION,
            "required_tools": list(REQUIRED_EXACT_SNAPSHOT_TOOLS),
            "required_dependency_tool": REQUIRED_DEPENDENCY_TOOL,
            "requested_tools": list(request["tools"]),
            "stale_client_tools_repaired": any(tool not in original for tool in REQUIRED_EXACT_SNAPSHOT_TOOLS),
            "execution_order_rule": "Current-tree and dependency evidence runs before full-history secret scanning so one expensive history operation cannot starve all later evidence categories.",
            "rule": "Exact-snapshot assessment scoring must request its current-tree, semantic-static, git-history, and cross-ecosystem dependency evidence tools even when a stale client sends an older explicit list.",
        }
    return result


def install_required_assessment_tools() -> dict[str, Any]:
    installed = bool(getattr(snapshot_worker, "_nico_required_assessment_tools_installed", False))
    snapshot_worker.start_snapshot_scan = start_snapshot_scan_with_required_tools
    snapshot_handlers.start_snapshot_scan = start_snapshot_scan_with_required_tools
    snapshot_worker._nico_required_assessment_tools_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": TOOL_POLICY_VERSION,
        "required_tools": list(REQUIRED_EXACT_SNAPSHOT_TOOLS),
        "required_dependency_tool": REQUIRED_DEPENDENCY_TOOL,
        "rule": "New Mid and Full exact-snapshot runs always request the evidence tools required by their active scoring model; unavailable execution remains disclosed rather than treated as clean or silently omitted.",
    }


__all__ = [
    "REQUIRED_DEPENDENCY_TOOL",
    "REQUIRED_EXACT_SNAPSHOT_TOOLS",
    "TOOL_POLICY_VERSION",
    "complete_assessment_tools",
    "install_required_assessment_tools",
    "start_snapshot_scan_with_required_tools",
]
