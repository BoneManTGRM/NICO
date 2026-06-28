from __future__ import annotations

from .permissions import permissions_for

APPROVAL_REQUIRED = {"production_mutation", "dependency_upgrade", "external_connector_access", "report_export", "secret_usage", "repo_setting_change", "hosted_saas_behavior", "high_risk_swarm_action"}


def can(role: str, permission: str, approved: bool = False) -> bool:
    if permission in APPROVAL_REQUIRED and not approved:
        return False
    return permission in permissions_for(role)


def require_permission(role: str, permission: str, approved: bool = False) -> dict:
    allowed = can(role, permission, approved)
    return {"allowed": allowed, "role": role, "permission": permission, "approval_required": permission in APPROVAL_REQUIRED and not approved}
