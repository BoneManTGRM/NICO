from __future__ import annotations

from nico.access.policy import require_permission

from .base import ConnectorRequest
from .policy import get_connector_policy


def evaluate_connector_request(request: ConnectorRequest) -> dict:
    policy = get_connector_policy(request.connector)
    if policy is None:
        return {"allowed": False, "reason": "unknown_connector"}
    if not policy.enabled:
        return {"allowed": False, "reason": "connector_disabled_by_default", "connector": policy.name}
    if request.operation in policy.blocked_operations:
        return {"allowed": False, "reason": "operation_blocked", "connector": policy.name}
    if request.operation not in policy.allowed_operations:
        return {"allowed": False, "reason": "operation_not_allowed", "connector": policy.name}
    if policy.secret_reference_required and not request.has_secret_reference:
        return {"allowed": False, "reason": "secret_reference_required", "connector": policy.name}
    permission = require_permission(request.role, "external_connector_access", approved=request.approved)
    if not permission["allowed"]:
        return {"allowed": False, "reason": "role_or_approval_denied", "connector": policy.name}
    return {"allowed": True, "reason": "connector_request_approved", "connector": policy.name}
