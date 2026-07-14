from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import nico.hosted_assessment as hosted
from nico.hosted_api_complexity_fallback import (
    _CAPTURED_PROFILE,
    attach_api_sample_complexity,
    fetch_repository_profile_with_complexity,
)


_EXPRESS_PROFILE_ENABLED: ContextVar[bool] = ContextVar(
    "nico_express_api_complexity_profile_enabled",
    default=False,
)


def install_hosted_api_complexity_fallback() -> dict[str, Any]:
    """Install a context-scoped Express profile dispatcher.

    Outside an Express invocation the dispatcher delegates directly to the original
    repository-profile collector, preserving Full/Mid and test-client contracts.
    """

    installed = bool(getattr(hosted, "_nico_api_complexity_fallback_compat_installed", False))
    if installed:
        return {
            "status": "already_installed",
            "version": "nico-hosted-api-complexity-fallback-v3",
            "shared_profile_override": False,
            "concurrent_express_requests_supported": True,
        }

    original_run = hosted.run_github_assessment
    original_profile_fetcher = hosted.fetch_repository_profile
    hosted._nico_original_run_github_assessment_api_complexity = original_run
    hosted._nico_original_fetch_repository_profile_api_complexity = original_profile_fetcher

    def profile_dispatcher(client: Any, repository: str, repo_meta: dict[str, Any]) -> dict[str, Any]:
        if _EXPRESS_PROFILE_ENABLED.get():
            return fetch_repository_profile_with_complexity(client, repository, repo_meta)
        return original_profile_fetcher(client, repository, repo_meta)

    def run_github_assessment_with_api_complexity(payload: dict[str, Any]) -> dict[str, Any]:
        capture_token = _CAPTURED_PROFILE.set(None)
        enabled_token = _EXPRESS_PROFILE_ENABLED.set(True)
        try:
            result = original_run(payload)
            return attach_api_sample_complexity(result, _CAPTURED_PROFILE.get())
        finally:
            _EXPRESS_PROFILE_ENABLED.reset(enabled_token)
            _CAPTURED_PROFILE.reset(capture_token)

    hosted.fetch_repository_profile = profile_dispatcher
    hosted.run_github_assessment = run_github_assessment_with_api_complexity
    try:
        from nico.api import main as api_main

        api_main.run_github_assessment = run_github_assessment_with_api_complexity
    except Exception:
        pass
    hosted._nico_api_complexity_fallback_compat_installed = True
    return {
        "status": "installed",
        "version": "nico-hosted-api-complexity-fallback-v3",
        "shared_profile_override": False,
        "context_scoped_express_profile": True,
        "concurrent_express_requests_supported": True,
        "truth_boundary": "The dispatcher uses the balanced collector only inside the active Express context; Full/Mid and other callers retain the original profile behavior.",
    }


__all__ = ["install_hosted_api_complexity_fallback"]
