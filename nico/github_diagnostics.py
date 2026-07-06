from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from nico.hosted_assessment import GitHubAssessmentClient

REDACTED = "[REDACTED]"


def _reset(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return "unavailable"


def github_auth_diagnostics() -> dict[str, Any]:
    client = GitHubAssessmentClient()
    has_auth = "Authorization" in client.headers
    try:
        response = requests.get("https://api.github.com/rate_limit", headers=client.headers, timeout=8)
        payload = response.json() if response.content else {}
    except Exception:
        return {
            "status": "ok",
            "github_auth_configured": has_auth,
            "github_auth_active": False,
            "github_metadata_confidence": "unavailable",
            "github_rate_limit_remaining": "unavailable",
            "github_rate_limit_reset": "unavailable",
            "credential": REDACTED if has_auth else "not_configured",
        }
    core = payload.get("resources", {}).get("core", {}) if isinstance(payload, dict) else {}
    limit = core.get("limit", response.headers.get("x-ratelimit-limit", "unavailable"))
    remaining = core.get("remaining", response.headers.get("x-ratelimit-remaining", "unavailable"))
    reset = core.get("reset", response.headers.get("x-ratelimit-reset", ""))
    active = has_auth and response.status_code == 200 and str(limit).isdigit() and int(limit) > 60
    return {
        "status": "ok",
        "github_auth_configured": has_auth,
        "github_auth_active": active,
        "github_metadata_confidence": "high" if active else ("limited" if response.status_code == 200 else "unavailable"),
        "github_rate_limit_remaining": remaining,
        "github_rate_limit_limit": limit,
        "github_rate_limit_reset": _reset(reset),
        "credential": REDACTED if has_auth else "not_configured",
        "raw_provider_error_json": "redacted",
    }
