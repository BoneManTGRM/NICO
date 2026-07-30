from __future__ import annotations

from dataclasses import replace
from typing import Any

import nico.scanner_tool_runners as scanner_module

VERSION = "nico.scanner-command-repair.v1"
_BANDIT_EXCLUDES = "tests,test,fixtures,fixture,examples,example,samples,sample,generated,vendor,vendors,dist,build,coverage,node_modules,.next,.venv,venv,audit-results"


def install_scanner_command_repair() -> dict[str, Any]:
    repaired = []
    changed = False
    for spec in scanner_module.TOOL_SPECS:
        if spec.name == "bandit":
            command = ("bandit", "-r", ".", "-f", "json", "-x", _BANDIT_EXCLUDES)
            repaired.append(replace(spec, command=command, timeout_seconds=max(spec.timeout_seconds, 360)))
            changed = changed or spec.command != command
        else:
            repaired.append(spec)
    scanner_module.TOOL_SPECS = tuple(repaired)
    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "bandit_exclusions_explicit": True,
        "bandit_rules_skipped": False,
    }


__all__ = ["VERSION", "install_scanner_command_repair"]
