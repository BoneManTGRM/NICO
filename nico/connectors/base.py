from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConnectorPolicy:
    name: str
    allowed_scopes: tuple[str, ...]
    required_role: str
    required_approval_level: str
    allowed_operations: tuple[str, ...]
    blocked_operations: tuple[str, ...]
    secret_reference_required: bool = True
    audit_required: bool = True
    enabled: bool = False


@dataclass
class ConnectorRequest:
    connector: str
    operation: str
    role: str
    approved: bool = False
    has_secret_reference: bool = False
    tenant_id: str = "local"
    metadata: dict = field(default_factory=dict)
