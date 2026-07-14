from __future__ import annotations

import os
from urllib.parse import urlsplit


REQUIRED_FRONTEND_ORIGINS = (
    "http://localhost:3000",
    "https://app.nicoaudit.com",
    "https://nicoaudit.vercel.app",
)


def _canonical_origin(value: str) -> str | None:
    text = str(value or "").strip().rstrip("/")
    if not text or text == "*":
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    if parsed.path not in {"", "/"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def required_frontend_cors_origins(configured: str | None = None) -> list[str]:
    """Return a bounded explicit origin allowlist for NICO's browser clients."""

    candidates = [*REQUIRED_FRONTEND_ORIGINS]
    candidates.extend(str(configured or "").split(","))
    result: list[str] = []
    for candidate in candidates:
        origin = _canonical_origin(candidate)
        if origin and origin not in result:
            result.append(origin)
    return result


def install_required_frontend_cors_origins() -> dict[str, object]:
    origins = required_frontend_cors_origins(os.getenv("NICO_CORS_ORIGINS", ""))
    os.environ["NICO_CORS_ORIGINS"] = ",".join(origins)
    return {
        "status": "installed",
        "version": "nico-required-frontend-cors-v1",
        "origins": origins,
        "wildcard_allowed": False,
        "credentials_in_origin_allowed": False,
        "truth_boundary": (
            "The production frontend origins remain explicitly allowed. "
            "This does not allow arbitrary origins or bypass assessment authorization."
        ),
    }


__all__ = [
    "REQUIRED_FRONTEND_ORIGINS",
    "install_required_frontend_cors_origins",
    "required_frontend_cors_origins",
]
