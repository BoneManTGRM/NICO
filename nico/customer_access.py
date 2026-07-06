from __future__ import annotations

from typing import Any

ROLES = {"owner", "admin", "reviewer", "viewer"}
ROLE_PERMISSIONS = {
    "owner": {"scan", "upload", "approve", "draft_pr", "report", "view"},
    "admin": {"scan", "upload", "approve", "report", "view"},
    "reviewer": {"upload", "approve", "report", "view"},
    "viewer": {"report", "view"},
}


def normalize_role(role: str | None) -> str:
    value = (role or "viewer").lower().strip()
    return value if value in ROLES else "viewer"


def can(role: str | None, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(normalize_role(role), set())


def access_summary(user: dict[str, Any] | None = None) -> dict[str, Any]:
    role = normalize_role((user or {}).get("role"))
    return {"role": role, "permissions": sorted(ROLE_PERMISSIONS[role]), "roles": sorted(ROLES)}
