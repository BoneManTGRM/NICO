from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CyberTwinNode:
    node_id: str
    node_type: str
    label: str
    tenant_id: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CyberTwinLink:
    from_node: str
    to_node: str
    relation: str
    tenant_id: str = "local"


@dataclass(frozen=True)
class CyberTwinGraph:
    nodes: tuple[CyberTwinNode, ...]
    links: tuple[CyberTwinLink, ...]
    tenant_id: str = "local"

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "nodes": [node.__dict__ for node in self.nodes],
            "links": [link.__dict__ for link in self.links],
        }
