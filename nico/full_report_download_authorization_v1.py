from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping

VERSION = "full_report_download_authorization_v1"
_ALLOWED_ROLES = {"owner", "admin", "auditor", "client_reviewer"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def authorize_full_download(
    response: Mapping[str, Any],
    *,
    actor_id: str,
    actor_role: str,
    workspace_id: str,
    assessment_workspace_id: str,
    request_id: str,
) -> dict[str, Any]:
    response_data = deepcopy(dict(response))
    issues: list[str] = []
    actor = _text(actor_id)
    role = _text(actor_role).lower()
    workspace = _text(workspace_id)
    assessment_workspace = _text(assessment_workspace_id)
    request = _text(request_id)

    if not actor:
        issues.append("missing_actor_id")
    if role not in _ALLOWED_ROLES:
        issues.append("role_not_authorized")
    if not workspace or not assessment_workspace:
        issues.append("missing_workspace_identity")
    elif workspace != assessment_workspace:
        issues.append("workspace_identity_mismatch")
    if not request:
        issues.append("missing_request_id")
    if not response_data.get("client_delivery_allowed"):
        issues.append("download_response_not_approved")

    artifact = response_data.get("artifact") if isinstance(response_data.get("artifact"), dict) else {}
    artifact_id = _text(artifact.get("artifact_id"))
    checksum = _text(artifact.get("sha256"))
    if not artifact_id:
        issues.append("missing_artifact_id")
    if not checksum:
        issues.append("missing_artifact_checksum")

    allowed = not issues
    event_seed = "|".join((request, actor, role, workspace, artifact_id, checksum, "allow" if allowed else "deny"))
    audit_event_id = sha256(event_seed.encode("utf-8")).hexdigest()
    return {
        "version": VERSION,
        "status": "authorized" if allowed else "blocked",
        "issues": issues,
        "client_delivery_allowed": allowed,
        "authorization": {
            "actor_id": actor,
            "actor_role": role,
            "workspace_id": workspace,
            "request_id": request,
        },
        "audit_event": {
            "audit_event_id": audit_event_id,
            "decision": "allow" if allowed else "deny",
            "artifact_id": artifact_id or None,
            "artifact_sha256": checksum or None,
            "request_id": request or None,
            "actor_id": actor or None,
            "workspace_id": workspace or None,
            "issues": list(issues),
        },
        "response": response_data if allowed else None,
    }


def attach_full_download_authorization(
    result: dict[str, Any],
    *,
    actor_id: str,
    actor_role: str,
    workspace_id: str,
    assessment_workspace_id: str,
    request_id: str,
) -> dict[str, Any]:
    response = result.get("full_download_response") if isinstance(result.get("full_download_response"), dict) else {}
    decision = authorize_full_download(
        response,
        actor_id=actor_id,
        actor_role=actor_role,
        workspace_id=workspace_id,
        assessment_workspace_id=assessment_workspace_id,
        request_id=request_id,
    )
    result["full_download_authorization"] = decision
    result["client_delivery_allowed"] = bool(result.get("client_delivery_allowed")) and decision["client_delivery_allowed"]
    return result


__all__ = ["VERSION", "attach_full_download_authorization", "authorize_full_download"]
