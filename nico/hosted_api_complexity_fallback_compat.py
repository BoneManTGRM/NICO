from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Callable

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


def _bind_runtime(
    profile_dispatcher: Callable[[Any, str, dict[str, Any]], dict[str, Any]],
    assessment_runner: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Restore the dispatcher if a later compatibility installer rebinds collectors."""

    hosted.fetch_repository_profile = profile_dispatcher
    hosted.run_github_assessment = assessment_runner
    try:
        from nico.api import main as api_main

        api_main.run_github_assessment = assessment_runner
    except Exception:
        pass


def install_hosted_api_complexity_fallback() -> dict[str, Any]:
    """Install a context-scoped Express profile dispatcher.

    Outside an Express invocation the dispatcher delegates directly to the original
    repository-profile collector, preserving Full/Mid and test-client contracts.
    Repeated installation also repairs the runtime binding if another compatibility
    installer restored the shared collector after this dispatcher was installed.
    """

    installed = bool(getattr(hosted, "_nico_api_complexity_fallback_compat_installed", False))
    existing_dispatcher = getattr(hosted, "_nico_api_complexity_profile_dispatcher", None)
    existing_runner = getattr(hosted, "_nico_api_complexity_assessment_runner", None)
    if installed and callable(existing_dispatcher) and callable(existing_runner):
        binding_repaired = bool(
            hosted.fetch_repository_profile is not existing_dispatcher
            or hosted.run_github_assessment is not existing_runner
        )
        _bind_runtime(existing_dispatcher, existing_runner)
        return {
            "status": "already_installed",
            "version": "nico-hosted-api-complexity-fallback-v3",
            "shared_profile_override": False,
            "context_scoped_express_profile": True,
            "concurrent_express_requests_supported": True,
            "runtime_binding_repaired": binding_repaired,
        }

    original_run = getattr(
        hosted,
        "_nico_original_run_github_assessment_api_complexity",
        hosted.run_github_assessment,
    )
    original_profile_fetcher = getattr(
        hosted,
        "_nico_original_fetch_repository_profile_api_complexity",
        hosted.fetch_repository_profile,
    )
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

    hosted._nico_api_complexity_profile_dispatcher = profile_dispatcher
    hosted._nico_api_complexity_assessment_runner = run_github_assessment_with_api_complexity
    _bind_runtime(profile_dispatcher, run_github_assessment_with_api_complexity)
    hosted._nico_api_complexity_fallback_compat_installed = True
    return {
        "status": "installed",
        "version": "nico-hosted-api-complexity-fallback-v3",
        "shared_profile_override": False,
        "context_scoped_express_profile": True,
        "concurrent_express_requests_supported": True,
        "runtime_binding_repaired": False,
        "truth_boundary": "The dispatcher uses the balanced collector only inside the active Express context; Full/Mid and other callers retain the original profile behavior.",
    }


__all__ = ["install_hosted_api_complexity_fallback"]
