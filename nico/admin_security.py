from __future__ import annotations

import hmac
import os
import secrets
from typing import Any

ADMIN_TOKEN_ENV = "NICO_ADMIN_TOKEN"
_INTERNAL_ADMIN_TOKEN = secrets.token_urlsafe(48)


def internal_admin_token() -> str:
    """Return the process-local authority used only by trusted in-process workflows.

    The value is generated at process start, is never returned by an API, is not
    stored, and is distinct from the operator-configured admin token. This lets a
    guarded server workflow complete its own report/approval setup without
    weakening public admin endpoints or requiring a browser to know a secret.
    """

    return _INTERNAL_ADMIN_TOKEN


def _is_internal_admin_token(provided_token: str | None) -> bool:
    return bool(provided_token) and hmac.compare_digest(str(provided_token), _INTERNAL_ADMIN_TOKEN)


def admin_write_status(provided_token: str | None = None) -> dict[str, Any]:
    """Return a safe, non-secret operator admin write status.

    NICO keeps public/operator admin writes disabled unless a server-side token is
    configured and the request supplies the matching token. Process-local internal
    authority is handled separately by ``require_admin_write`` and is never
    disclosed through this status function.
    """

    configured = bool(os.getenv(ADMIN_TOKEN_ENV, "").strip())
    if not configured:
        return {
            "enabled": False,
            "status": "read_only",
            "reason": f"{ADMIN_TOKEN_ENV} is not configured; operator admin writes are disabled.",
        }
    allowed = bool(provided_token) and hmac.compare_digest(str(provided_token), os.getenv(ADMIN_TOKEN_ENV, ""))
    return {
        "enabled": allowed,
        "status": "enabled" if allowed else "blocked",
        "reason": "Admin token accepted." if allowed else "Admin token is required for this write action.",
    }


def require_admin_write(provided_token: str | None = None) -> tuple[bool, dict[str, Any]]:
    if _is_internal_admin_token(provided_token):
        return True, {
            "enabled": True,
            "status": "internal",
            "reason": "Trusted process-local workflow authority accepted.",
            "publicly_usable": False,
        }
    status = admin_write_status(provided_token)
    if status["enabled"]:
        return True, status
    return False, {
        "status": "unavailable",
        "mode": "read_only",
        "configured": status["status"] != "read_only",
        "admin_write": status,
    }


def safe_public_admin_status() -> dict[str, Any]:
    status = admin_write_status(None)
    return {
        "admin_writes_configured": status["status"] != "read_only",
        "admin_writes_publicly_enabled": False,
        "admin_write_mode": status["status"],
        "note": "Writable admin endpoints require server-side operator authentication. Process-local workflow authority is not exposed to clients.",
    }


__all__ = [
    "ADMIN_TOKEN_ENV",
    "admin_write_status",
    "internal_admin_token",
    "require_admin_write",
    "safe_public_admin_status",
]
