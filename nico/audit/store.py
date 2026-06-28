from __future__ import annotations

from dataclasses import dataclass, field

from nico.security.masking import mask_text

from .events import AuditEvent


@dataclass
class InMemoryAuditStore:
    events: list[AuditEvent] = field(default_factory=list)

    def append(self, event: AuditEvent) -> AuditEvent:
        safe_detail = {key: mask_text(str(value)) for key, value in event.detail.items()}
        safe_event = AuditEvent(
            action=event.action,
            actor=event.actor,
            tenant_id=event.tenant_id,
            risk_level=event.risk_level,
            approval_required=event.approval_required,
            detail=safe_detail,
            created_at=event.created_at,
        )
        self.events.append(safe_event)
        return safe_event

    def latest(self, tenant_id: str = "local") -> list[AuditEvent]:
        return [event for event in self.events if event.tenant_id == tenant_id]
