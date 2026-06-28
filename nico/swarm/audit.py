from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AgentMessageAudit:
    agent_from: str
    agent_to: str
    task: str
    tools_requested: tuple[str, ...] = ()
    files_accessed: tuple[str, ...] = ()
    risk_level: str = "low"
    approval_required: bool = False
    result: str = "recorded"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
