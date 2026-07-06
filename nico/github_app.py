from __future__ import annotations

from typing import Any

REQUIRED_READ_PERMISSIONS = {
    "metadata": "read",
    "contents": "read",
    "pull_requests": "read",
    "issues": "read",
    "actions": "read",
    "checks": "read",
}

OPTIONAL_WRITE_PERMISSIONS = {
    "contents": "write for draft repair branches only",
    "pull_requests": "write for draft PR creation only",
    "issues": "write for approval-gated issue creation only",
}


def github_app_plan() -> dict[str, Any]:
    return {
        "status": "planned",
        "mode": "read_only_first",
        "required_read_permissions": REQUIRED_READ_PERMISSIONS,
        "optional_future_permissions": OPTIONAL_WRITE_PERMISSIONS,
        "rules": [
            "Never expose installation tokens to the browser.",
            "Support selected repositories only.",
            "Start with read-only access.",
            "Only create draft PRs after human approval and optional write permission is enabled.",
        ],
    }


def installation_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "recorded_stub",
        "installation_id": payload.get("installation_id") or "pending",
        "customer_id": payload.get("customer_id") or "default_customer",
        "selected_repositories": payload.get("selected_repositories") or [],
        "permissions": payload.get("permissions") or REQUIRED_READ_PERMISSIONS,
        "unavailable_data_notes": ["GitHub App OAuth/installation exchange is not enabled in this safe architecture stub."],
    }
