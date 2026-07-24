from __future__ import annotations

import os
import re
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.runtime_deployment_commit_resolution.v1"
_MARKER = "_nico_runtime_deployment_commit_resolution_v1"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _repository(value: Any) -> str:
    candidate = _text(value)
    return candidate if _REPOSITORY_RE.fullmatch(candidate) else ""


def _expected_sha(context: Mapping[str, Any]) -> str:
    for key in ("expected_commit_sha", "commit_sha", "snapshot_commit_sha"):
        value = _text(context.get(key)).lower()
        if _SHA_RE.fullmatch(value):
            return value
    return ""


def _provider_candidates(environ: Mapping[str, str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    railway_sha = _text(environ.get("RAILWAY_GIT_COMMIT_SHA")).lower()
    railway_owner = _text(environ.get("RAILWAY_GIT_REPO_OWNER"))
    railway_name = _text(environ.get("RAILWAY_GIT_REPO_NAME"))
    railway_repository = _repository(f"{railway_owner}/{railway_name}" if railway_owner and railway_name else "")
    if _SHA_RE.fullmatch(railway_sha) and railway_repository:
        candidates.append(
            {
                "provider": "railway",
                "repository": railway_repository,
                "commit_sha": railway_sha,
                "branch": _text(environ.get("RAILWAY_GIT_BRANCH")),
                "source": "railway_runtime_deployment",
                "method": "railway_git_commit_sha",
            }
        )

    vercel_sha = _text(environ.get("VERCEL_GIT_COMMIT_SHA")).lower()
    vercel_owner = _text(environ.get("VERCEL_GIT_REPO_OWNER"))
    vercel_name = _text(environ.get("VERCEL_GIT_REPO_SLUG"))
    vercel_repository = _repository(f"{vercel_owner}/{vercel_name}" if vercel_owner and vercel_name else "")
    if _SHA_RE.fullmatch(vercel_sha) and vercel_repository:
        candidates.append(
            {
                "provider": "vercel",
                "repository": vercel_repository,
                "commit_sha": vercel_sha,
                "branch": _text(environ.get("VERCEL_GIT_COMMIT_REF")),
                "source": "vercel_runtime_deployment",
                "method": "vercel_git_commit_sha",
            }
        )
    return candidates


def runtime_deployment_resolution(
    context: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return exact immutable identity when the running provider proves it.

    Only provider-owned Git variables are accepted. The repository owner/name and
    exact 40-character commit must both match the assessment request. A mismatch is
    never converted into success; callers continue to the existing API/Git resolver.
    """

    repository = _repository(context.get("repository"))
    expected = _expected_sha(context)
    if not repository or not expected:
        return None

    for candidate in _provider_candidates(environ or os.environ):
        if candidate["repository"].casefold() != repository.casefold():
            continue
        if candidate["commit_sha"] != expected:
            continue
        return {
            "status": "attached",
            "repository": repository,
            "source": candidate["source"],
            "commit_capture_method": candidate["method"],
            "api_commit_lookup_attempts": 0,
            "public_git_fallback_attempted": False,
            "public_git_fallback_used": False,
            "repository_metadata_available": True,
            "default_branch": candidate["branch"],
            "requested_ref": expected,
            "expected_commit_sha": expected,
            "commit_binding_source": "provider_runtime_deployment",
            "exact_commit_verified": True,
            "commit_sha": expected,
            "tree_sha": "",
            "commit_date": "",
            "commit_message": "",
            "repository_pushed_at": "",
            "repository_visibility": "provider_deployment_verified",
            "deployment_provider": candidate["provider"],
            "deployment_repository_verified": True,
            "deployment_commit_verified": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    return None


def install_runtime_deployment_commit_resolution() -> dict[str, Any]:
    from nico import exact_commit_binding, repository_snapshot
    from nico.comprehensive_cross_format_finality_v49 import (
        install_comprehensive_cross_format_finality_v49,
    )

    cross_format_finality = install_comprehensive_cross_format_finality_v49()
    current: Callable[..., dict[str, Any]] = repository_snapshot.resolve_repository_commit
    if getattr(current, _MARKER, False):
        exact_commit_binding.resolve_repository_commit = current
        return {
            "status": "already_installed",
            "version": VERSION,
            "repository_snapshot_bound": True,
            "exact_commit_binding_bound": True,
            "comprehensive_cross_format_finality": cross_format_finality,
        }

    @wraps(current)
    def resolve(context: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
        runtime = runtime_deployment_resolution(context)
        if runtime is not None:
            return runtime
        return current(context, client=client)

    setattr(resolve, _MARKER, True)
    setattr(resolve, "_nico_previous", current)
    repository_snapshot.resolve_repository_commit = resolve
    exact_commit_binding.resolve_repository_commit = resolve
    return {
        "status": "installed",
        "version": VERSION,
        "repository_snapshot_bound": repository_snapshot.resolve_repository_commit is resolve,
        "exact_commit_binding_bound": exact_commit_binding.resolve_repository_commit is resolve,
        "provider_owned_variables_only": True,
        "repository_identity_required": True,
        "exact_sha_match_required": True,
        "api_and_public_git_fallback_preserved": True,
        "comprehensive_cross_format_finality": cross_format_finality,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_runtime_deployment_commit_resolution",
    "runtime_deployment_resolution",
]
