from __future__ import annotations

import os
from typing import Any

ADMIN_TOKEN_ENV = "NICO_ADMIN_TOKEN"


def admin_write_status(provided_token: str | None = None) -> dict[str, Any]:
    """Return a safe, non-secret admin write status.

    NICO keeps admin writes disabled unless a server-side token is configured and
    the request supplies the matching token. The token itself is never returned.
    """
    configured = bool(os.getenv(ADMIN_TOKEN_ENV, "").strip())
    if not configured:
        return {
            "enabled": False,
            "status": "read_only",
            "reason": f"{ADMIN_TOKEN_ENV} is not configured; admin writes are disabled.",
        }
    allowed = bool(provided_token) and provided_token == os.getenv(ADMIN_TOKEN_ENV)
    return {
        "enabled": allowed,
        "status": "enabled" if allowed else "blocked",
        "reason": "Admin token accepted." if allowed else "Admin token is required for this write action.",
    }


def require_admin_write(provided_token: str | None = None) -> tuple[bool, dict[str, Any]]:
    status = admin_write_status(provided_token)
    if status["enabled"]:
        return True, status
    return False, {"status": "unavailable", "mode": "read_only", "admin_write": status}


def safe_public_admin_status() -> dict[str, Any]:
    status = admin_write_status(None)
    return {
        "admin_writes_configured": status["status"] != "read_only",
        "admin_writes_publicly_enabled": False,
        "admin_write_mode": status["status"],
        "note": "Writable admin endpoints require server-side admin authentication. Hiding frontend buttons is not security.",
    }
