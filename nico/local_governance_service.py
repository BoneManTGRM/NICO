from __future__ import annotations

from typing import Any


def decide_action(action: str, policy: dict[str, Any]) -> dict[str, Any]:
    """Apply the existing fail-closed local action policy without side effects."""

    if policy.get("kill_switch"):
        return {
            "allowed": False,
            "reason": "kill switch enabled",
            "requires_approval": True,
        }
    if action in policy.get("blocked_actions", []):
        return {
            "allowed": False,
            "reason": "blocked by defensive policy",
            "requires_approval": False,
        }
    if action in policy.get("approval_required", []):
        return {
            "allowed": False,
            "reason": "human approval required",
            "requires_approval": True,
        }
    if action in policy.get("allowed_actions", []):
        return {
            "allowed": True,
            "reason": "allowed",
            "requires_approval": False,
        }
    return {
        "allowed": False,
        "reason": "unknown action denied by default",
        "requires_approval": True,
    }


__all__ = ["decide_action"]
