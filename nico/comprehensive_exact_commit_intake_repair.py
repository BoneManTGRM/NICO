from __future__ import annotations

import re
from functools import wraps
from typing import Any
from urllib.parse import quote

VERSION = "nico.comprehensive_exact_commit_intake_repair.v1"
_PATCH_MARKER = "_nico_comprehensive_exact_commit_intake_repair_v1"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _valid_commit(value: Any, expected: str) -> bool:
    return (
        isinstance(value, dict)
        and str(value.get("sha") or "").strip().lower() == expected.lower()
    )


def _git_commit_fallback(client: Any, repository: str, expected: str) -> tuple[dict[str, Any] | None, str | None]:
    get_json = getattr(client, "get_json", None)
    repo_url = getattr(client, "repo_url", None)
    if not callable(get_json) or not callable(repo_url):
        return None, "GitHub exact-commit fallback is unavailable."

    git_commit, git_error = get_json(
        repo_url(repository, f"/git/commits/{quote(expected, safe='')}")
    )
    if isinstance(git_commit, dict) and str(git_commit.get("sha") or "").strip().lower() == expected:
        return {
            "sha": expected,
            "commit": {
                "message": git_commit.get("message") or "Exact commit verified through the GitHub Git database API.",
                "author": git_commit.get("author") if isinstance(git_commit.get("author"), dict) else {},
                "committer": git_commit.get("committer") if isinstance(git_commit.get("committer"), dict) else {},
                "tree": git_commit.get("tree") if isinstance(git_commit.get("tree"), dict) else {},
            },
            "verification_source": "github_git_commit_api",
        }, None

    contents, contents_error = get_json(
        repo_url(repository, "/contents"),
        {"ref": expected},
    )
    if not contents_error and isinstance(contents, (dict, list)):
        return {
            "sha": expected,
            "commit": {
                "message": "Exact commit verified through the GitHub repository contents API.",
                "author": {},
                "committer": {},
                "tree": {},
            },
            "verification_source": "github_contents_exact_ref",
        }, None

    return None, str(contents_error or git_error or "Exact commit could not be verified through GitHub.")


def install_comprehensive_exact_commit_intake_repair() -> dict[str, Any]:
    from nico import repository_snapshot

    current = repository_snapshot._get_commit
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def get_commit_with_exact_ref_fallback(
        client: Any,
        repository: str,
        ref: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        commit, error = current(client, repository, ref)
        expected = str(ref or "").strip().lower()
        if not _SHA_RE.fullmatch(expected) or _valid_commit(commit, expected):
            return commit, error

        fallback, fallback_error = _git_commit_fallback(client, repository, expected)
        if fallback is not None:
            return fallback, None
        return commit, error or fallback_error

    setattr(get_commit_with_exact_ref_fallback, _PATCH_MARKER, True)
    setattr(get_commit_with_exact_ref_fallback, "_nico_previous", current)
    repository_snapshot._get_commit = get_commit_with_exact_ref_fallback
    return {
        "status": "installed",
        "version": VERSION,
        "exact_sha_only": True,
        "primary_commit_endpoint_preserved": True,
        "git_database_fallback": True,
        "contents_exact_ref_fallback": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_exact_commit_intake_repair"]
