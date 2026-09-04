import hashlib
import hmac
import os
import secrets

ADMIN_TOKEN_ENV = "NICO_ADMIN_TOKEN"
COMPREHENSIVE_OPERATOR_PASSWORD_ENV = "NICO_COMPREHENSIVE_OPERATOR_PASSWORD"
# Backward compatibility for the already-deployed owner-controlled pilot password.
SARA_OPERATOR_PASSWORD_ENV = "NICO_SARA_OPERATOR_PASSWORD"
_PASSWORD_HASH_PREFIX = "scrypt_v1"
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def _configured_admin_token() -> str:
    return os.getenv(ADMIN_TOKEN_ENV, "").strip()


def _configured_comprehensive_operator_passwords() -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    generic = os.getenv(COMPREHENSIVE_OPERATOR_PASSWORD_ENV, "").strip()
    legacy = os.getenv(SARA_OPERATOR_PASSWORD_ENV, "").strip()
    if generic:
        values.append((generic, "nico_comprehensive_operator"))
    if legacy and not any(hmac.compare_digest(legacy, value) for value, _ in values):
        values.append((legacy, "sara_comprehensive_operator"))
    return values


def _configured_sara_operator_password() -> str:
    """Compatibility accessor retained for existing callers and tests."""

    return os.getenv(SARA_OPERATOR_PASSWORD_ENV, "").strip()


def hash_sara_operator_password(
    password: str,
    *,
    salt: bytes | None = None,
) -> str:
    """Return a salted, CPU/memory-hard verifier for a plain operator password.

    The plain form remains accepted for one deploy so Railway can be migrated without
    downtime. New secrets should use this verifier form rather than a raw password.
    """

    supplied = str(password or "")
    if not supplied:
        raise ValueError("sara_operator_password_required")
    salt_bytes = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
    if len(salt_bytes) < _SALT_BYTES:
        raise ValueError("sara_operator_password_salt_too_short")
    digest = hashlib.scrypt(
        supplied.encode("utf-8"),
        salt=salt_bytes,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_BYTES,
    )
    return f"{_PASSWORD_HASH_PREFIX}${salt_bytes.hex()}${digest.hex()}"


def _verify_scrypt_password(supplied: str, configured: str) -> bool:
    parts = configured.split("$")
    if len(parts) != 3 or parts[0] != _PASSWORD_HASH_PREFIX:
        return False
    try:
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
    except ValueError:
        return False
    if len(salt) < _SALT_BYTES or len(expected) != _KEY_BYTES:
        return False
    try:
        observed = hashlib.scrypt(
            supplied.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(observed, expected)


def _matches_operator_password(supplied: str, configured: str) -> bool:
    if configured.startswith(f"{_PASSWORD_HASH_PREFIX}$"):
        return _verify_scrypt_password(supplied, configured)
    # Transitional compatibility. Replace the Railway value with
    # hash_sara_operator_password(...) after the first successful deployment.
    return hmac.compare_digest(supplied, configured)


def safe_public_admin_status():
    return {
        "configured": bool(_configured_admin_token()),
        "write_authority": "server_secret_required",
        "token_exposed": False,
    }


def require_admin_write(supplied_token: str | None):
    configured = _configured_admin_token()
    supplied = (supplied_token or "").strip()
    if configured and supplied and hmac.compare_digest(configured, supplied):
        return True, {
            "status": "authorized",
            "authority": "admin_token",
            "admin_write_allowed": True,
        }
    return False, {
        "status": "blocked",
        "reason": "admin_authentication_required",
        "admin_configured": bool(configured),
        "admin_write_allowed": False,
    }


def require_comprehensive_operator(supplied_token: str | None):
    """Authorize the bounded Comprehensive specialist workflow.

    The site-wide admin token remains valid. A separate NICO operator password grants
    only Comprehensive assessment, review, approval, and delivery authority. The
    legacy environment name remains accepted during migration so existing operators
    are not locked out.
    """

    supplied = (supplied_token or "").strip()
    admin_allowed, admin_status = require_admin_write(supplied)
    if admin_allowed:
        return True, {
            **admin_status,
            "scope": "comprehensive_review_and_delivery",
        }

    for configured, authority in _configured_comprehensive_operator_passwords():
        if supplied and _matches_operator_password(supplied, configured):
            return True, {
                "status": "authorized",
                "authority": authority,
                "scope": "comprehensive_review_and_delivery",
                "admin_write_allowed": False,
            }

    return False, {
        "status": "blocked",
        "reason": "comprehensive_operator_authentication_required",
        "admin_configured": bool(_configured_admin_token()),
        "operator_password_configured": bool(_configured_comprehensive_operator_passwords()),
        "admin_write_allowed": False,
        "scope": "comprehensive_review_and_delivery",
    }
