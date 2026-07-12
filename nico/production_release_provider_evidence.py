from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import nico.production_release_gate as release_gate

PROVIDER_ORIGIN_MATCHING_VERSION = "nico.production_release_provider_evidence.v1"
PROVIDER_DOMAINS = {
    "vercel": ("vercel.com",),
    "railway": ("railway.com",),
}

_INSTALLED = False
_ORIGINAL_PROVIDER_SUMMARY = release_gate.provider_summary


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _provider_origin(value: Any) -> str:
    return release_gate.safe_origin(value)


def _provider_host(origin: str) -> str:
    if not origin:
        return ""
    try:
        return str(urlsplit(origin).hostname or "").lower()
    except ValueError:
        return ""


def _host_matches(provider: str, origin: str) -> bool:
    host = _provider_host(origin)
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in PROVIDER_DOMAINS.get(provider, ()))


def provider_observations(check_runs: list[Any], commit_statuses: list[Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for raw in check_runs:
        item = _dict(raw)
        name = str(item.get("name") or "").strip()
        raw_url = item.get("html_url") or item.get("details_url") or ""
        if name:
            observations.append(
                {
                    "source": "check_run",
                    "name": name,
                    "status": str(item.get("status") or "unknown").lower(),
                    "conclusion": str(item.get("conclusion") or "unknown").lower(),
                    "url": _provider_origin(raw_url),
                }
            )
    for raw in commit_statuses:
        item = _dict(raw)
        name = str(item.get("context") or item.get("name") or "").strip()
        if name:
            observations.append(
                {
                    "source": "commit_status",
                    "name": name,
                    "status": "completed",
                    "conclusion": str(item.get("state") or "unknown").lower(),
                    "url": _provider_origin(item.get("target_url") or ""),
                }
            )
    return observations


def provider_summary(check_runs: list[Any], commit_statuses: list[Any]) -> dict[str, dict[str, Any]]:
    observations = provider_observations(check_runs, commit_statuses)
    result: dict[str, dict[str, Any]] = {}
    for provider, patterns in release_gate.REQUIRED_PROVIDERS.items():
        matches = [
            item
            for item in observations
            if any(pattern in str(item.get("name") or "").lower() for pattern in patterns)
            or _host_matches(provider, str(item.get("url") or ""))
        ]
        successes = [
            item
            for item in matches
            if item.get("status") == "completed" and item.get("conclusion") in {"success", "neutral"}
        ]
        result[provider] = {
            "provider": provider,
            "matched": bool(matches),
            "passed": bool(successes),
            "observations": matches,
            "matching_version": PROVIDER_ORIGIN_MATCHING_VERSION,
        }
    return result


def install_provider_origin_matching() -> dict[str, Any]:
    global _INSTALLED
    if _INSTALLED:
        return {
            "installed": True,
            "idempotent_reuse": True,
            "version": PROVIDER_ORIGIN_MATCHING_VERSION,
        }
    release_gate._provider_observations = provider_observations
    release_gate.provider_summary = provider_summary
    _INSTALLED = True
    return {
        "installed": True,
        "idempotent_reuse": False,
        "version": PROVIDER_ORIGIN_MATCHING_VERSION,
        "provider_domains": {key: list(value) for key, value in PROVIDER_DOMAINS.items()},
    }


PROVIDER_ORIGIN_MATCHING = install_provider_origin_matching()

PRODUCTION_RELEASE_GATE_SCHEMA = release_gate.PRODUCTION_RELEASE_GATE_SCHEMA
FRONTEND_DEPLOYMENT_SCHEMA = release_gate.FRONTEND_DEPLOYMENT_SCHEMA
REQUIRED_WORKFLOWS = release_gate.REQUIRED_WORKFLOWS
REQUIRED_PROVIDERS = release_gate.REQUIRED_PROVIDERS
normalize_sha = release_gate.normalize_sha
sha_matches = release_gate.sha_matches
safe_origin = release_gate.safe_origin
workflow_summary = release_gate.workflow_summary
build_production_release_manifest = release_gate.build_production_release_manifest

__all__ = [
    "PROVIDER_ORIGIN_MATCHING_VERSION",
    "PROVIDER_DOMAINS",
    "PROVIDER_ORIGIN_MATCHING",
    "PRODUCTION_RELEASE_GATE_SCHEMA",
    "FRONTEND_DEPLOYMENT_SCHEMA",
    "REQUIRED_WORKFLOWS",
    "REQUIRED_PROVIDERS",
    "normalize_sha",
    "sha_matches",
    "safe_origin",
    "workflow_summary",
    "provider_observations",
    "provider_summary",
    "build_production_release_manifest",
    "install_provider_origin_matching",
]
