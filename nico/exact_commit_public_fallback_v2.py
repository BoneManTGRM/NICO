from __future__ import annotations

import re
from typing import Any, Callable

VERSION = "nico.exact_commit_public_fallback.v2"
_MARKER = "_nico_exact_commit_public_fallback_v2"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def resolve_commit_with_public_fallback(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Resolve the exact requested commit without weakening identity guarantees.

    The GitHub API remains primary. For a repository that GitHub metadata confirms is
    public, a bounded credential-free Git fetch may verify the same requested
    40-character SHA when the API commit lookup is exhausted or transiently
    unavailable. A mismatched API response never falls back and private repositories
    remain API-only.
    """

    from nico.exact_commit_binding import expected_commit_sha
    from nico.hosted_assessment import GitHubAssessmentClient, normalize_repository
    from nico.repository_snapshot import (
        _public_git_exact_commit,
        _public_repository,
        _retry_commit_lookup,
    )

    repository = normalize_repository(str(payload.get("repository") or ""))
    client = GitHubAssessmentClient()
    repo_meta, repo_error = client.get_repo(repository)
    if repo_error or not repo_meta:
        return repository, "", (
            "Repository metadata unavailable while binding the immutable commit: "
            f"{repo_error or 'unknown error'}"
        )

    requested = expected_commit_sha(payload)
    default_branch = str(repo_meta.get("default_branch") or "main")
    ref = requested or default_branch
    commit, commit_error, attempts = _retry_commit_lookup(client, repository, ref)
    resolved = str((commit or {}).get("sha") or "").strip().lower()
    api_mismatch = bool(requested and _SHA_RE.fullmatch(resolved) and resolved != requested)

    if api_mismatch:
        return repository, "", (
            f"GitHub resolved {requested} to a different commit ({resolved}); assessment stopped fail-closed."
        )

    if (commit_error or not _SHA_RE.fullmatch(resolved)) and requested and _public_repository(repo_meta):
        fallback, fallback_error = _public_git_exact_commit(repository, requested)
        fallback_sha = str((fallback or {}).get("sha") or "").strip().lower()
        if fallback and fallback_sha == requested and _SHA_RE.fullmatch(fallback_sha):
            return repository, fallback_sha, ""
        return repository, "", (
            "The exact requested public commit could not be verified after "
            f"{attempts} GitHub API attempt(s) and the bounded public Git fallback: "
            f"{fallback_error or commit_error or 'invalid commit response'}"
        )

    if commit_error or not _SHA_RE.fullmatch(resolved):
        return repository, "", (
            "The requested repository commit could not be resolved through the authorized GitHub API scope after "
            f"{attempts} attempt(s): {commit_error or 'invalid commit response'}"
        )
    return repository, resolved, ""


def install_exact_commit_public_fallback_v2() -> dict[str, Any]:
    from nico import exact_commit_binding as target

    current: Callable[[dict[str, Any]], tuple[str, str, str]] = target._resolve_commit
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    setattr(resolve_commit_with_public_fallback, _MARKER, True)
    setattr(resolve_commit_with_public_fallback, "_nico_previous", current)
    target._resolve_commit = resolve_commit_with_public_fallback
    return {
        "status": "installed",
        "version": VERSION,
        "github_api_primary": True,
        "bounded_api_retries": True,
        "public_git_exact_sha_fallback": True,
        "private_repository_fallback_allowed": False,
        "api_mismatch_fallback_allowed": False,
        "exact_sha_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_exact_commit_public_fallback_v2",
    "resolve_commit_with_public_fallback",
]
