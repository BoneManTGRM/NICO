from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from nico.hosted_assessment import GitHubAssessmentClient, _iso, _now
from nico.storage import STORE, StorageAdapter

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_EXACT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SAFE_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_EXPECTED_MARKER_RE = re.compile(r"(?:^|[;\s])expected_commit_sha=([0-9a-fA-F]{40})(?:$|[;\s])")
_API_COMMIT_ATTEMPTS = 3
_API_RETRY_DELAYS_SECONDS = (0.25, 0.75)


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def repository_snapshot_id(run_id: str, repository: str) -> str:
    material = f"github-repository-snapshot|{run_id}|{repository}".encode("utf-8")
    return f"snapshot_github_{hashlib.sha256(material).hexdigest()[:20]}"


def _short(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _expected_commit_sha(context: dict[str, Any]) -> tuple[str, str]:
    for key in ("expected_commit_sha", "commit_sha", "snapshot_commit_sha"):
        raw = str(context.get(key) or "").strip()
        if not raw:
            continue
        if not _EXACT_SHA_RE.fullmatch(raw):
            return "", "invalid_explicit_commit_sha"
        return raw.lower(), "explicit_request"
    marker = str(context.get("authorized_by") or "")
    match = _EXPECTED_MARKER_RE.search(marker)
    if match:
        return match.group(1).lower(), "authorized_request_marker"
    return "", "default_branch_resolved_once"


def _get_commit(client: Any, repository: str, ref: str) -> tuple[dict[str, Any] | None, str | None]:
    method = getattr(client, "get_commit", None)
    if callable(method):
        value, error = method(repository, ref)
        return (value if isinstance(value, dict) else None), error
    get_json = getattr(client, "get_json", None)
    repo_url = getattr(client, "repo_url", None)
    if not callable(get_json) or not callable(repo_url):
        return None, "GitHub commit lookup is unavailable."
    value, error = get_json(repo_url(repository, f"/commits/{quote(ref, safe='')}"))
    return (value if isinstance(value, dict) else None), error


def _retry_commit_lookup(
    client: Any,
    repository: str,
    ref: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any] | None, str | None, int]:
    last_error: str | None = None
    for attempt in range(1, _API_COMMIT_ATTEMPTS + 1):
        commit, error = _get_commit(client, repository, ref)
        if commit and not error:
            return commit, None, attempt
        last_error = error or "GitHub commit lookup returned no commit."
        if attempt <= len(_API_RETRY_DELAYS_SECONDS):
            sleep(_API_RETRY_DELAYS_SECONDS[attempt - 1])
    return None, last_error, _API_COMMIT_ATTEMPTS


def _git_command(
    command: list[str],
    *,
    timeout: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
    }
    return runner(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=environment,
    )


def _public_git_exact_commit(
    repository: str,
    expected_sha: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[dict[str, Any] | None, str | None]:
    """Verify one exact anonymously accessible commit without API quota.

    A successful credential-free fetch proves that the requested repository object is
    publicly reachable. Private repositories fail closed because anonymous fetch cannot
    retrieve the object. The exact 40-character SHA is verified byte-for-byte.
    """

    if not _SAFE_REPOSITORY_RE.fullmatch(repository):
        return None, "public_git_invalid_repository"
    if not _EXACT_SHA_RE.fullmatch(expected_sha):
        return None, "public_git_invalid_commit_sha"

    repository_url = f"https://github.com/{repository}.git"
    try:
        with tempfile.TemporaryDirectory(prefix="nico-public-snapshot-") as temporary:
            git_dir = Path(temporary) / "repository.git"
            initialized = _git_command(
                ["git", "-c", "credential.helper=", "init", "--bare", str(git_dir)],
                timeout=20,
                runner=runner,
            )
            if initialized.returncode != 0:
                return None, "public_git_initialize_failed"

            fetched = _git_command(
                [
                    "git",
                    "-c",
                    "credential.helper=",
                    "-c",
                    "http.extraHeader=",
                    "--git-dir",
                    str(git_dir),
                    "fetch",
                    "--depth=1",
                    "--no-tags",
                    repository_url,
                    expected_sha,
                ],
                timeout=60,
                runner=runner,
            )
            if fetched.returncode != 0:
                return None, "public_git_exact_sha_fetch_failed"

            described = _git_command(
                [
                    "git",
                    "--git-dir",
                    str(git_dir),
                    "show",
                    "-s",
                    "--format=%H%x00%T%x00%cI%x00%s",
                    "FETCH_HEAD",
                ],
                timeout=20,
                runner=runner,
            )
            if described.returncode != 0:
                return None, "public_git_commit_description_failed"
            fields = described.stdout.rstrip("\n").split("\x00", 3)
            if len(fields) != 4:
                return None, "public_git_commit_description_invalid"
            commit_sha, tree_sha, commit_date, message = fields
            commit_sha = commit_sha.strip().lower()
            tree_sha = tree_sha.strip().lower()
            if commit_sha != expected_sha.lower() or not _EXACT_SHA_RE.fullmatch(commit_sha):
                return None, "public_git_commit_mismatch"
            if tree_sha and not _SHA_RE.fullmatch(tree_sha):
                return None, "public_git_tree_sha_invalid"
            return {
                "sha": commit_sha,
                "commit": {
                    "committer": {"date": commit_date.strip()},
                    "author": {"date": commit_date.strip()},
                    "tree": {"sha": tree_sha},
                    "message": message.strip(),
                },
            }, None
    except (OSError, subprocess.SubprocessError):
        return None, "public_git_execution_failed"


def _public_repository(repo_meta: dict[str, Any]) -> bool:
    if repo_meta.get("private") is False:
        return True
    return str(repo_meta.get("visibility") or "").strip().lower() == "public"


def _preverified_resolution(
    context: dict[str, Any],
    repository: str,
    expected_sha: str,
) -> dict[str, Any] | None:
    value = context.get("exact_commit_resolution")
    if not isinstance(value, dict) or value.get("status") != "attached":
        return None
    resolved_repository = str(value.get("repository") or "").strip()
    commit_sha = str(value.get("commit_sha") or "").strip().lower()
    resolved_expected = str(value.get("expected_commit_sha") or commit_sha).strip().lower()
    if resolved_repository.lower() != repository.lower():
        return None
    if not _EXACT_SHA_RE.fullmatch(commit_sha):
        return None
    if expected_sha and commit_sha != expected_sha:
        return None
    if resolved_expected and resolved_expected != commit_sha:
        return None
    if value.get("exact_commit_verified") is not True:
        return None
    return dict(value)


def resolve_repository_commit(
    context: dict[str, Any],
    *,
    client: GitHubAssessmentClient | None = None,
) -> dict[str, Any]:
    """Resolve one immutable commit through API or anonymous exact-SHA Git proof.

    API metadata remains authoritative when available. If metadata or commit lookup is
    rate-limited and an explicit SHA is present, anonymous Git may prove public access
    and the exact object identity. API mismatches and repositories confirmed private
    never use the fallback.
    """

    repository = str(context.get("repository") or "").strip()
    expected_sha, binding_source = _expected_commit_sha(context)
    if binding_source == "invalid_explicit_commit_sha":
        return {
            "status": "unavailable",
            "repository": repository,
            "expected_commit_sha": "",
            "commit_binding_source": binding_source,
            "resolution_failure_code": "invalid_explicit_commit_sha",
            "unavailable_data_notes": ["The explicitly requested immutable commit SHA was invalid."],
        }
    if not repository or not _SAFE_REPOSITORY_RE.fullmatch(repository):
        return {
            "status": "unavailable",
            "repository": repository,
            "expected_commit_sha": expected_sha,
            "commit_binding_source": binding_source,
            "resolution_failure_code": "invalid_repository",
            "unavailable_data_notes": ["A normalized owner/repository target is required for immutable commit resolution."],
        }

    github = client or GitHubAssessmentClient()
    repo_meta, repo_error = github.get_repo(repository)
    metadata_available = bool(isinstance(repo_meta, dict) and repo_meta and not repo_error)
    repo_meta = repo_meta if isinstance(repo_meta, dict) else {}
    confirmed_private = metadata_available and not _public_repository(repo_meta)
    default_branch = str(repo_meta.get("default_branch") or "main") if metadata_available else ""
    requested_ref = expected_sha or default_branch

    commit: dict[str, Any] | None = None
    commit_error: str | None = repo_error or None
    api_attempts = 0
    commit_capture_method = ""
    api_mismatch = False
    fallback_attempted = False
    fallback_error = ""

    if metadata_available and requested_ref:
        commit, commit_error, api_attempts = _retry_commit_lookup(github, repository, requested_ref)
        api_sha = str((commit or {}).get("sha") or "").strip().lower()
        api_mismatch = bool(expected_sha and api_sha and api_sha != expected_sha)
        if commit and not commit_error and _SHA_RE.fullmatch(api_sha) and not api_mismatch:
            commit_capture_method = "github_api_commit"

    fallback_allowed = bool(expected_sha and not api_mismatch and not confirmed_private)
    if not commit_capture_method and fallback_allowed:
        fallback_attempted = True
        fallback, fallback_error = _public_git_exact_commit(repository, expected_sha)
        if fallback:
            commit = fallback
            commit_error = None
            commit_capture_method = "public_git_exact_sha"

    commit_sha = str((commit or {}).get("sha") or "").strip().lower()
    mismatch = bool(expected_sha and commit_sha and commit_sha != expected_sha)
    if not commit_capture_method or commit_error or not _SHA_RE.fullmatch(commit_sha) or mismatch:
        if mismatch or api_mismatch:
            failure_code = "repository_commit_mismatch"
        elif confirmed_private:
            failure_code = "private_repository_api_commit_unavailable"
        elif not metadata_available and not expected_sha:
            failure_code = "repository_metadata_unavailable"
        else:
            failure_code = fallback_error or "repository_commit_unavailable"
        return {
            "status": "unavailable",
            "repository": repository,
            "default_branch": default_branch,
            "requested_ref": requested_ref,
            "expected_commit_sha": expected_sha,
            "commit_binding_source": binding_source,
            "repository_metadata_available": metadata_available,
            "repository_confirmed_private": confirmed_private,
            "api_commit_lookup_attempts": api_attempts,
            "public_git_fallback_attempted": fallback_attempted,
            "resolution_failure_code": failure_code,
            "unavailable_data_notes": [
                "The exact requested commit could not be verified through the GitHub API or credential-free exact-SHA Git transport."
                if expected_sha and fallback_attempted
                else "The exact requested commit could not be verified through the authorized GitHub API scope."
                if expected_sha
                else "The default-branch commit could not be resolved because repository metadata was unavailable."
            ],
        }

    commit_payload = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
    committer = commit_payload.get("committer") if isinstance(commit_payload.get("committer"), dict) else {}
    author = commit_payload.get("author") if isinstance(commit_payload.get("author"), dict) else {}
    tree = commit_payload.get("tree") if isinstance(commit_payload.get("tree"), dict) else {}
    visibility = str(repo_meta.get("visibility") or "").strip().lower()
    if not visibility:
        visibility = "public_verified_by_anonymous_git" if commit_capture_method == "public_git_exact_sha" else "unknown"
    return {
        "status": "attached",
        "repository": repository,
        "source": "github_api_read_only" if commit_capture_method == "github_api_commit" else "public_git_read_only",
        "commit_capture_method": commit_capture_method,
        "api_commit_lookup_attempts": api_attempts,
        "public_git_fallback_attempted": fallback_attempted,
        "public_git_fallback_used": commit_capture_method == "public_git_exact_sha",
        "repository_metadata_available": metadata_available,
        "default_branch": default_branch,
        "requested_ref": requested_ref or commit_sha,
        "expected_commit_sha": expected_sha or commit_sha,
        "commit_binding_source": binding_source,
        "exact_commit_verified": True,
        "commit_sha": commit_sha,
        "tree_sha": str(tree.get("sha") or "").lower(),
        "commit_date": str(committer.get("date") or author.get("date") or ""),
        "commit_message": _short(commit_payload.get("message"), 180),
        "repository_pushed_at": str(repo_meta.get("pushed_at") or ""),
        "repository_visibility": visibility,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def capture_repository_snapshot(
    context: dict[str, Any],
    *,
    client: GitHubAssessmentClient | None = None,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    """Capture one immutable commit identity for an assessment run."""

    run_id = str(context.get("run_id") or "").strip()
    repository = str(context.get("repository") or "").strip()
    customer_id = str(context.get("customer_id") or "default_customer")
    project_id = str(context.get("project_id") or "default_project")
    snapshot_id = repository_snapshot_id(run_id, repository)
    expected_sha, binding_source = _expected_commit_sha(context)
    if binding_source == "invalid_explicit_commit_sha":
        return {
            "status": "unavailable",
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": customer_id,
            "project_id": project_id,
            "unavailable_data_notes": ["The explicitly requested immutable commit SHA was invalid."],
            "idempotent_reuse": False,
            "human_review_required": True,
        }
    if not run_id or not repository:
        return {
            "status": "unavailable",
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "unavailable_data_notes": ["A run ID and repository are required before a repository snapshot can be captured."],
            "idempotent_reuse": False,
        }

    active_store = _store(store)
    existing = active_store.get("evidence_items", snapshot_id)
    existing_snapshot = existing.get("evidence") if isinstance(existing, dict) and isinstance(existing.get("evidence"), dict) else None
    if existing_snapshot and existing_snapshot.get("status") == "attached":
        reused = dict(existing_snapshot)
        reused["idempotent_reuse"] = True
        return reused

    resolution = _preverified_resolution(context, repository, expected_sha)
    if resolution is None:
        resolution = resolve_repository_commit(context, client=client)
    if resolution.get("status") != "attached":
        return {
            "status": "unavailable",
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": customer_id,
            "project_id": project_id,
            "source": str(resolution.get("source") or "github_api_read_only"),
            "default_branch": str(resolution.get("default_branch") or ""),
            "requested_ref": str(resolution.get("requested_ref") or expected_sha),
            "expected_commit_sha": expected_sha,
            "commit_binding_source": binding_source,
            "api_commit_lookup_attempts": int(resolution.get("api_commit_lookup_attempts") or 0),
            "public_git_fallback_attempted": bool(resolution.get("public_git_fallback_attempted")),
            "repository_metadata_available": bool(resolution.get("repository_metadata_available")),
            "snapshot_failure_code": str(resolution.get("resolution_failure_code") or "repository_snapshot_commit_unavailable"),
            "unavailable_data_notes": list(resolution.get("unavailable_data_notes") or ["The exact repository commit could not be captured."]),
            "idempotent_reuse": False,
            "human_review_required": True,
        }

    snapshot = {
        **resolution,
        "snapshot_id": snapshot_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "captured_at": _iso(_now()),
        "idempotent_reuse": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "All repository file evidence and scanner execution for this run must use this exact commit SHA or be marked unavailable.",
    }
    active_store.put(
        "evidence_items",
        snapshot_id,
        {
            "evidence_id": snapshot_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "run_id": run_id,
            "filename": "github-repository-snapshot.json",
            "content_type": "application/json",
            "source": snapshot["source"],
            "repository": repository,
            "evidence": snapshot,
        },
    )
    active_store.audit(
        "assessment.repository_snapshot_captured",
        {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "default_branch": snapshot.get("default_branch", ""),
            "requested_ref": snapshot.get("requested_ref", ""),
            "expected_commit_sha": snapshot.get("expected_commit_sha", ""),
            "commit_binding_source": snapshot.get("commit_binding_source", binding_source),
            "commit_capture_method": snapshot.get("commit_capture_method", ""),
            "api_commit_lookup_attempts": snapshot.get("api_commit_lookup_attempts", 0),
            "repository_metadata_available": snapshot.get("repository_metadata_available", False),
            "commit_sha": snapshot.get("commit_sha", ""),
            "tree_sha": snapshot.get("tree_sha", ""),
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return snapshot


__all__ = [
    "capture_repository_snapshot",
    "repository_snapshot_id",
    "resolve_repository_commit",
]
