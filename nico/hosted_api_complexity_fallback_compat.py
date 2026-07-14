from __future__ import annotations

import threading
from typing import Any

import nico.hosted_assessment as hosted
from nico.hosted_api_complexity_fallback import (
    _CAPTURED_PROFILE,
    attach_api_sample_complexity,
    fetch_repository_profile_with_complexity,
)


_EXPRESS_PROFILE_LOCK = threading.RLock()


def install_hosted_api_complexity_fallback() -> dict[str, Any]:
    """Install the API complexity fallback without replacing shared profile collection."""

    installed = bool(getattr(hosted, "_nico_api_complexity_fallback_compat_installed", False))
    if installed:
        return {
            "status": "already_installed",
            "version": "nico-hosted-api-complexity-fallback-v2",
            "shared_profile_override": False,
        }

    original_run = hosted.run_github_assessment
    original_profile_fetcher = hosted.fetch_repository_profile
    hosted._nico_original_run_github_assessment_api_complexity = original_run
    hosted._nico_original_fetch_repository_profile_api_complexity = original_profile_fetcher

    def run_github_assessment_with_api_complexity(payload: dict[str, Any]) -> dict[str, Any]:
        token = _CAPTURED_PROFILE.set(None)
        try:
            # The legacy assessment function resolves its profile collector from the
            # hosted module at call time. Scope that substitution to one serialized
            # Express invocation and restore it before returning. Full/Mid evidence
            # collectors keep the original function and their fake-client contract.
            with _EXPRESS_PROFILE_LOCK:
                active_fetcher = hosted.fetch_repository_profile
                hosted.fetch_repository_profile = fetch_repository_profile_with_complexity
                try:
                    result = original_run(payload)
                finally:
                    hosted.fetch_repository_profile = active_fetcher
            return attach_api_sample_complexity(result, _CAPTURED_PROFILE.get())
        finally:
            _CAPTURED_PROFILE.reset(token)

    hosted.run_github_assessment = run_github_assessment_with_api_complexity
    try:
        from nico.api import main as api_main

        api_main.run_github_assessment = run_github_assessment_with_api_complexity
    except Exception:
        pass
    hosted._nico_api_complexity_fallback_compat_installed = True
    return {
        "status": "installed",
        "version": "nico-hosted-api-complexity-fallback-v2",
        "shared_profile_override": False,
        "serialized_express_profile_scope": True,
        "truth_boundary": "The balanced complexity collector is scoped to one Express request; shared Full/Mid repository evidence collection is unchanged.",
    }


__all__ = ["install_hosted_api_complexity_fallback"]
