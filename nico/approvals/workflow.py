from __future__ import annotations

from dataclasses import dataclass

from .policy import approval_required


@dataclass(frozen=True)
class ApprovalDecision:
    action: str
    allowed: bool
    reason: str


def evaluate_action(action: str, risk_level: str = "low", approved: bool = False) -> ApprovalDecision:
    required = approval_required(action, risk_level)
    if required and not approved:
        return ApprovalDecision(action=action, allowed=False, reason="human_approval_required")
    return ApprovalDecision(action=action, allowed=True, reason="allowed_for_local_foundation")
