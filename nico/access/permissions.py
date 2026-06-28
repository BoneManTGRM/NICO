from __future__ import annotations

ROLE_PERMISSIONS = {
    "owner": {"scan", "report", "repair_plan", "export", "settings", "connectors", "vault", "approval", "audit", "swarm_supervision", "production_mutation"},
    "admin": {"scan", "report", "repair_plan", "settings", "connectors", "approval", "audit", "swarm_supervision"},
    "analyst": {"scan", "report", "repair_plan", "audit"},
    "developer": {"scan", "report", "repair_plan"},
    "viewer": {"report"},
}


def permissions_for(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, set()))
