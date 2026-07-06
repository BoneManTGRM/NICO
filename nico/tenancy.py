from __future__ import annotations

from typing import Any


def scoped_ids(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
    }


def enforce_scope(item: dict[str, Any], customer_id: str | None = None, project_id: str | None = None) -> bool:
    if customer_id and item.get("customer_id") != customer_id:
        return False
    if project_id and item.get("project_id") != project_id:
        return False
    return True


def authorization_record(payload: dict[str, Any]) -> dict[str, Any]:
    ids = scoped_ids(payload)
    return {
        **ids,
        "authorized_by": payload.get("authorized_by") or "unspecified",
        "authorized_target": payload.get("repository") or payload.get("target") or "unspecified",
        "authorization_scope": payload.get("authorization_scope") or "assessment only",
        "code_modification_allowed": bool(payload.get("code_modification_allowed", False)),
        "draft_pr_creation_allowed": bool(payload.get("draft_pr_creation_allowed", False)),
        "evidence_uploads_allowed": bool(payload.get("evidence_uploads_allowed", True)),
    }
