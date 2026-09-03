from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Any

ADMIN_TOKEN_ENV = "NICO_ADMIN_TOKEN"
SARA_OPERATOR_PASSWORD_ENV = "NICO_SARA_OPERATOR_PASSWORD"
SARA_OPERATOR_PASSWORD_SHA256_ENV = "NICO_SARA_OPERATOR_PASSWORD_SHA256"
# This verifier is safe to publish: the corresponding 256-bit password exists
# only in SARA's production secret store.
DEPLOYED_SARA_OPERATOR_PASSWORD_SHA256 = "282e0db5774a2613bf34e5bc25fde8df2ea180c59b261495cd67ba1d40e1207a"
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


def require_comprehensive_operator(provided_token: str | None = None) -> tuple[bool, dict[str, Any]]:
    """Authorize only Comprehensive review and delivery operations.

    SARA's service password is deliberately not accepted by ``require_admin_write``.
    It therefore cannot administer projects, runtime configuration, recovery,
    backups, or any other NICO operator surface.
    """

    admin_allowed, admin_status = require_admin_write(provided_token)
    if admin_allowed:
        authority = (
            "nico_internal"
            if admin_status.get("status") == "internal"
            else "nico_admin"
        )
        return True, {
            **admin_status,
            "authority": authority,
            "scope": "comprehensive_review_and_delivery",
        }
    configured = os.getenv(SARA_OPERATOR_PASSWORD_ENV, "").strip()
    configured_digest = (
        os.getenv(SARA_OPERATOR_PASSWORD_SHA256_ENV, "").strip().lower()
        or DEPLOYED_SARA_OPERATOR_PASSWORD_SHA256
    )
    digest_configured = bool(
        len(configured_digest) == 64
        and all(character in "0123456789abcdef" for character in configured_digest)
    )
    provided_digest = hashlib.sha256(str(provided_token or "").encode("utf-8")).hexdigest()
    allowed = (
        bool(configured and provided_token)
        and hmac.compare_digest(str(provided_token), configured)
    ) or (
        bool(provided_token)
        and digest_configured
        and hmac.compare_digest(provided_digest, configured_digest)
    )
    if allowed:
        return True, {
            "enabled": True,
            "status": "enabled",
            "authority": "sara_comprehensive_operator",
            "scope": "comprehensive_review_and_delivery",
            "reason": "Scoped SARA Comprehensive operator accepted.",
        }
    return False, {
        "status": "unavailable",
        "mode": "read_only",
        "configured": bool(configured or digest_configured),
        "scope": "comprehensive_review_and_delivery",
        "reason": "Comprehensive operator authentication is required.",
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
    "SARA_OPERATOR_PASSWORD_ENV",
    "SARA_OPERATOR_PASSWORD_SHA256_ENV",
    "admin_write_status",
    "internal_admin_token",
    "require_admin_write",
    "require_comprehensive_operator",
    "safe_public_admin_status",
]
