from __future__ import annotations

from pathlib import Path
from typing import Any

import nico.exact_snapshot_secret_history as history

_ORIGINAL_RUN_HISTORY_TOOL = history._run_history_tool


def guarded_run_history_tool(
    name: str,
    cfg: dict[str, Any],
    repo_path: Path,
    env: dict[str, str],
    deadline: float,
) -> dict[str, Any]:
    result = dict(_ORIGINAL_RUN_HISTORY_TOOL(name, cfg, repo_path, env, deadline))
    exit_code = result.get("exit_code")
    finding_count = int(result.get("finding_count") or 0)
    if result.get("execution_completed") is True and exit_code not in {0, None} and finding_count == 0:
        result["status"] = "failed"
        result["execution_status"] = "execution_failed"
        result["execution_completed"] = False
        result["risk_severity"] = "unknown"
        result["evidence_summary"] = (
            f"{name} returned nonzero exit code {exit_code} without a parseable finding report; "
            "the run is an execution failure, not clean evidence."
        )
        notes = [str(item) for item in result.get("unavailable_data_notes") or [] if str(item)]
        notes.append("Nonzero empty scanner output cannot support a clean git-history claim.")
        result["unavailable_data_notes"] = list(dict.fromkeys(notes))
    return result


def install_secret_history_exit_guard() -> dict[str, Any]:
    installed = bool(getattr(history, "_nico_secret_history_exit_guard_installed", False))
    history._run_history_tool = guarded_run_history_tool
    history._nico_secret_history_exit_guard_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "rule": "A nonzero git-history scanner exit with zero parseable findings is an execution failure and never a clean result.",
    }


__all__ = ["guarded_run_history_tool", "install_secret_history_exit_guard"]
