from __future__ import annotations

from .events import AuditEvent


def audit_summary(events: list[AuditEvent]) -> dict:
    return {
        "event_count": len(events),
        "approval_required_count": sum(1 for event in events if event.approval_required),
        "high_risk_count": sum(1 for event in events if event.risk_level in {"high", "critical"}),
    }
