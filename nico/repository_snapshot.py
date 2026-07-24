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


def _git_environment(workspace: Path) -> dict[str, str]:
    """Build a bounded environment for anonymous Git execution.

    Git-specific process overrides are intentionally not inherited. This prevents
    request-adjacent runtime state from changing the transport, configuration,
    credential, hook, or executable behavior used by the exact-SHA proof path.
    """

    inherited_keys = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    )
    environment = {
        key: value
        for key in inherited_keys
        if (value := os.environ.get(key))
    }
    environment.update(
        {
            "HOME": str(workspace),
            "XDG_CONFIG_HOME": str(workspace / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS": "",
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_PROTOCOL_FROM_USER": "0",
        }
    )
    return environment


def _git_init_bare(
    git_dir: Path,
    environment: dict[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    return runner(
        ["git", "-c", "credential.helper=", "-c", "http.extraHeader=", "init", "--bare", "."],
        cwd=str(git_dir),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        shell=False,
        env=environment,
    )


def _configure_public_origin(git_dir: Path, repository_url: str) -> None:
    if not repository_url.startswith("https://github.com/") or "\n" in repository_url or "\r" in repository_url:
        raise ValueError("invalid public GitHub repository URL")
    with (git_dir / "config").open("a", encoding="utf-8", newline="\n") as config:
        config.write(f'\n[remote "origin"]\n\turl = {repository_url}\n')


def _git_fetch_exact_sha(
    git_dir: Path,
    expected_sha: str,
    environment: dict[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    return runner(
        [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "http.extraHeader=",
            "fetch",
            "--depth=1",
            "--no-tags",
            "--stdin",
            "origin",
        ],
        cwd=str(git_dir),
        input=f"{expected_sha}\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        shell=False,
        env=environment,
    )


def _git_describe_fetch_head(
    git_dir: Path,
    environment: dict[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    return runner(
        ["git", "show", "-s", "--format=%H%x00%T%x00%cI%x00%s", "FETCH_HEAD"],
        cwd=str(git_dir),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        shell=False,
        env=environment,
    )


def _public_git_exact_commit(
    repository: str,
    expected_sha: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[dict[str, Any] | None, str | None]:
    """Verify one exact anonymously accessible commit without API quota.

    The subprocess command vectors are fixed literals. The validated repository URL
    is written to a temporary local Git configuration, and the validated exact SHA is
    supplied as fetch refspec input rather than becoming part of the command line.
    """

    if not _SAFE_REPOSITORY_RE.fullmatch(repository):
        return None, "public_git_invalid_repository"
    if not _EXACT_SHA_RE.fullmatch(expected_sha):
        return None, "public_git_invalid_commit_sha"

    repository_url = f"https://github.com/{repository}.git"
    try:
        with tempfile.TemporaryDirectory(prefix="nico-public-snapshot-") as temporary:
            workspace = Path(temporary)
            git_dir = workspace / "repository.git"
            git_dir.mkdir(mode=0o700)
            environment = _git_environment(workspace)

            initialized = _git_init_bare(git_dir, environment, runner=runner)
            if initialized.returncode != 0:
                return None, "public_git_initialize_failed"

            _configure_public_origin(git_dir, repository_url)
            fetched = _git_fetch_exact_sha(git_dir, expected_sha, environment, runner=runner)
            if fetched.returncode != 0:
                return None, "public_git_exact_sha_fetch_failed"

            described = _git_describe_fetch_head(git_dir, environment, runner=runner)
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
    except (OSError, ValueError, subprocess.SubprocessError):
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


def _legacy_snapshot_failure_code(value: Any) -> str:
    """Preserve the established snapshot API contract for existing consumers."""

    code = str(value or "").strip()
    aliases = {
        "repository_commit_mismatch": "repository_snapshot_commit_mismatch",
        "private_repository_api_commit_unavailable": "repository_snapshot_commit_unavailable",
        "repository_commit_unavailable": "repository_snapshot_commit_unavailable",
    }
    return aliases.get(code, code or "repository_snapshot_commit_unavailable")


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
                else "The exact default-branch commit could not be resolved because repository metadata was unavailable."
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
            "snapshot_failure_code": _legacy_snapshot_failure_code(resolution.get("resolution_failure_code")),
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
