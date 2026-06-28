from __future__ import annotations

from .models import CyberTwinGraph, CyberTwinLink, CyberTwinNode


def build_demo_cyber_twin() -> dict:
    graph = CyberTwinGraph(
        nodes=(
            CyberTwinNode("asset:local-workspace", "asset", "Local Demo Workspace"),
            CyberTwinNode("file:app", "file", "Application fixture"),
            CyberTwinNode("route:local-api", "route", "Local API fixture"),
            CyberTwinNode("dependency:demo", "dependency", "Demo dependency manifest"),
            CyberTwinNode("finding:masked", "finding", "Masked local finding"),
            CyberTwinNode("repair:tgrm", "repair", "TGRM repair plan"),
            CyberTwinNode("verification:local", "verification", "Local verification result"),
            CyberTwinNode("drift:demo", "drift", "Demo drift event"),
            CyberTwinNode("agent:scan", "agent", "Scan Agent action"),
            CyberTwinNode("audit:local", "audit", "Local audit event"),
        ),
        links=(
            CyberTwinLink("asset:local-workspace", "file:app", "contains"),
            CyberTwinLink("file:app", "route:local-api", "defines"),
            CyberTwinLink("file:app", "dependency:demo", "uses"),
            CyberTwinLink("file:app", "finding:masked", "has_finding"),
            CyberTwinLink("finding:masked", "repair:tgrm", "has_repair_plan"),
            CyberTwinLink("repair:tgrm", "verification:local", "verified_by"),
            CyberTwinLink("drift:demo", "finding:masked", "influences"),
            CyberTwinLink("agent:scan", "audit:local", "records"),
        ),
    )
    payload = graph.to_dict()
    payload["mode"] = "local_demo_only_no_external_discovery"
    return payload
