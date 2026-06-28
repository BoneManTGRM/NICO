from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nico.security.masking import mask_text

from .execution_policy import command_allowed, path_allowed


@dataclass(frozen=True)
class SandboxPlan:
    command: str
    working_directory: str
    timeout_seconds: int = 30
    network_allowed: bool = False


def validate_sandbox_plan(plan: SandboxPlan, allowed_root: str) -> dict:
    if not path_allowed(plan.working_directory, allowed_root):
        return {"allowed": False, "reason": "working_directory_outside_allowed_root"}
    decision = command_allowed(plan.command, network_allowed=plan.network_allowed)
    if not decision["allowed"]:
        return decision
    return {
        "allowed": True,
        "reason": "sandbox_plan_valid",
        "working_directory": str(Path(plan.working_directory)),
        "timeout_seconds": plan.timeout_seconds,
        "network_allowed": plan.network_allowed,
    }


def safe_scanner_output(output: str) -> str:
    return mask_text(output)
