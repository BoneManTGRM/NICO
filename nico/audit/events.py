from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(frozen=True)
class AuditEvent:
    action: str
    actor: str
    tenant_id: str = "local"
    risk_level: str = "low"
    approval_required: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
