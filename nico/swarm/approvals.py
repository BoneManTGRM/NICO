from __future__ import annotations

from nico.approvals.workflow import evaluate_action


def swarm_approval_required(action: str, risk_level: str = "low") -> bool:
    return not evaluate_action(action, risk_level=risk_level, approved=False).allowed
