from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import quote

from nico.hosted_assessment import GitHubAssessmentClient, _iso, _now
from nico.storage import STORE, StorageAdapter

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def repository_snapshot_id(run_id: str, repository: str) -> str:
    material = f"github-repository-snapshot|{run_id}|{repository}".encode("utf-8")
    return f"snapshot_github_{hashlib.sha256(material).hexdigest()[:20]}"


def _short(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


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


def capture_repository_snapshot(
    context: dict[str, Any],
    *,
    client: GitHubAssessmentClient | None = None,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    """Capture one immutable default-branch commit identity for an assessment run."""

    run_id = str(context.get("run_id") or "").strip()
    repository = str(context.get("repository") or "").strip()
    customer_id = str(context.get("customer_id") or "default_customer")
    project_id = str(context.get("project_id") or "default_project")
    snapshot_id = repository_snapshot_id(run_id, repository)
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

    github = client or GitHubAssessmentClient()
    repo_meta, repo_error = github.get_repo(repository)
    if repo_error or not repo_meta:
        return {
            "status": "unavailable",
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": customer_id,
            "project_id": project_id,
            "source": "github_api_read_only",
            "unavailable_data_notes": ["Repository metadata was unavailable through the authorized GitHub API scope."],
            "idempotent_reuse": False,
        }

    default_branch = str(repo_meta.get("default_branch") or "main")
    commit, commit_error = _get_commit(github, repository, default_branch)
    commit_sha = str((commit or {}).get("sha") or "")
    if commit_error or not commit or not _SHA_RE.fullmatch(commit_sha):
        return {
            "status": "unavailable",
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": customer_id,
            "project_id": project_id,
            "source": "github_api_read_only",
            "default_branch": default_branch,
            "unavailable_data_notes": ["The exact default-branch commit could not be captured through the authorized GitHub API scope."],
            "idempotent_reuse": False,
        }

    commit_payload = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
    committer = commit_payload.get("committer") if isinstance(commit_payload.get("committer"), dict) else {}
    author = commit_payload.get("author") if isinstance(commit_payload.get("author"), dict) else {}
    tree = commit_payload.get("tree") if isinstance(commit_payload.get("tree"), dict) else {}
    snapshot = {
        "status": "attached",
        "snapshot_id": snapshot_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": customer_id,
        "project_id": project_id,
        "source": "github_api_read_only",
        "captured_at": _iso(_now()),
        "default_branch": default_branch,
        "commit_sha": commit_sha.lower(),
        "tree_sha": str(tree.get("sha") or "").lower(),
        "commit_date": str(committer.get("date") or author.get("date") or ""),
        "commit_message": _short(commit_payload.get("message"), 180),
        "repository_pushed_at": str(repo_meta.get("pushed_at") or ""),
        "repository_visibility": str(repo_meta.get("visibility") or ("private" if repo_meta.get("private") else "public")),
        "idempotent_reuse": False,
        "human_review_required": True,
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
            "source": "github_api_read_only",
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
            "default_branch": default_branch,
            "commit_sha": commit_sha.lower(),
            "tree_sha": str(tree.get("sha") or "").lower(),
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return snapshot
