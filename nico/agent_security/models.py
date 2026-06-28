from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentConfig:
    name: str
    tools: tuple[str, ...] = ()
    memory_zones: tuple[str, ...] = ()
    can_mutate: bool = False
    can_export: bool = False
    requires_approval: bool = True
    connector_access: tuple[str, ...] = field(default_factory=tuple)
