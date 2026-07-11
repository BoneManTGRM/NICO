from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from nico.hosted_assessment import (
    GitHubAssessmentClient,
    _iso,
    _now,
    collect_dependencies,
    fetch_repository_profile,
    fetch_workflows,
    scan_files,
)
from nico.storage import STORE, StorageAdapter

DEFAULT_TIMEFRAME_DAYS = 180
DEPENDENCY_MANIFEST_NAMES = {
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
LOCKFILE_NAMES = {"Pipfile.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
DEPLOYMENT_NAMES = {"Dockerfile", "Procfile", "render.yaml", "railway.json", "fly.toml", "vercel.json"}
WORKFLOW_COMMANDS = ["pytest", "npm test", "npm run lint", "npm run build", "next build", "eslint", "mypy", "ruff", "semgrep", "bandit"]


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _evidence_id(run_id: str, repository: str) -> str:
    digest = hashlib.sha256(f"github-repository-evidence|{run_id}|{repository}".encode("utf-8")).hexdigest()[:20]
    return f"evidence_github_{digest}"


def _short_text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _safe_api_note(label: str, error: str | None) -> str:
    if not error:
        return f"{label} was unavailable through the GitHub API."
    lowered = error.lower()
    if "404" in lowered:
        return f"{label} was unavailable through the authorized GitHub API scope; verify repository access."
    if "401" in lowered or "403" in lowered:
        return f"{label} was unavailable because the GitHub credential or installation lacks required read access."
    if "rate" in lowered or "429" in lowered:
        return f"{label} was unavailable because the GitHub API rate limit was reached."
    return f"{label} was unavailable through the GitHub API."


def _safe_notes(label: str, notes: list[Any]) -> list[str]:
    return sorted({_safe_api_note(label, str(note)) for note in notes if note})


def _sample_commits(commits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for item in commits[:10]:
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        samples.append(
            {
                "sha": str(item.get("sha") or "")[:12],
                "date": author.get("date") or "",
                "message": _short_text(commit.get("message"), 160),
            }
        )
    return samples


def _sample_pulls(pulls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "number": item.get("number"),
            "state": item.get("state") or "unknown",
            "merged": bool(item.get("merged_at")),
            "updated_at": item.get("updated_at") or "",
            "title": _short_text(item.get("title"), 160),
        }
        for item in pulls[:10]
    ]


def _workflow_summary(workflows: dict[str, str], runs: list[dict[str, Any]]) -> dict[str, Any]:
    combined = "\n".join(workflows.values()).lower()
    success = sum(1 for item in runs if item.get("conclusion") == "success")
    non_success = sum(1 for item in runs if item.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"})
    commands = [command for command in WORKFLOW_COMMANDS if command in combined]
    return {
        "workflow_files": sorted(workflows.keys()),
        "workflow_file_count": len(workflows),
        "workflow_run_count": len(runs),
        "successful_runs": success,
        "non_success_runs": non_success,
        "commands_detected": commands,
        "explicit_permissions_present": "permissions:" in combined,
        "secret_references_present": "secrets." in combined,
    }


def _repository_summary(repo_meta: dict[str, Any], profile: dict[str, Any], files: dict[str, str]) -> dict[str, Any]:
    tree_paths = list(profile.get("tree_paths") or [])
    root_items = list(profile.get("root_items") or [])
    source_paths = [
        path
        for path in tree_paths
        if path.endswith((".py", ".ts", ".tsx", ".js", ".jsx"))
        and not path.startswith("tests/")
        and "test" not in path.rsplit("/", 1)[-1].lower()
    ]
    test_paths = [path for path in tree_paths if "test" in path.lower()]
    doc_paths = [path for path in tree_paths if path.lower().endswith(".md") or path.startswith("docs/")]
    deployment = [path for path in tree_paths if path.rsplit("/", 1)[-1] in DEPLOYMENT_NAMES]
    manifests = [path for path in files if path.rsplit("/", 1)[-1] in DEPENDENCY_MANIFEST_NAMES]
    lockfiles = [path for path in files if path.rsplit("/", 1)[-1] in LOCKFILE_NAMES]
    dependencies = collect_dependencies(files)
    ecosystems = sorted({str(item.get("ecosystem") or "unknown") for item in dependencies})
    return {
        "repository_metadata": {
            "full_name": repo_meta.get("full_name"),
            "default_branch": repo_meta.get("default_branch"),
            "visibility": repo_meta.get("visibility"),
            "private": bool(repo_meta.get("private")),
            "archived": bool(repo_meta.get("archived")),
            "language": repo_meta.get("language"),
            "size_kb": repo_meta.get("size"),
            "pushed_at": repo_meta.get("pushed_at"),
        },
        "file_evidence": {
            "files_profiled": len(files),
            "tree_paths_seen": len(tree_paths),
            "sampled_paths": sorted(files.keys())[:40],
            "top_level_items": sorted(root_items)[:40],
        },
        "architecture_evidence": {
            "source_file_count": len(source_paths),
            "test_path_count": len(test_paths),
            "documentation_path_count": len(doc_paths),
            "deployment_manifests": sorted(deployment)[:20],
            "top_level_directories": sorted(item for item in root_items if "." not in item)[:30],
        },
        "dependency_evidence": {
            "manifest_paths": sorted(manifests),
            "lockfile_paths": sorted(lockfiles),
            "dependency_entries": len(dependencies),
            "ecosystems": ecosystems,
        },
    }


def _persist(bundle: dict[str, Any], store: StorageAdapter) -> dict[str, Any]:
    evidence_id = str(bundle["evidence_id"])
    encoded = json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    store.put(
        "evidence_items",
        evidence_id,
        {
            "evidence_id": evidence_id,
            "customer_id": bundle.get("customer_id") or "default_customer",
            "project_id": bundle.get("project_id") or "default_project",
            "run_id": bundle.get("run_id") or "",
            "filename": "github-repository-evidence.json",
            "content_type": "application/json",
            "size_bytes": len(encoded),
            "source": "github_api_read_only",
            "repository": bundle.get("repository") or "",
            "evidence": bundle,
        },
    )
    return bundle


def collect_repository_evidence(
    context: dict[str, Any],
    *,
    client: GitHubAssessmentClient | None = None,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    """Collect a summarized, read-only GitHub evidence bundle for one full-run."""

    active_store = _store(store)
    run_id = str(context.get("run_id") or "").strip()
    repository = str(context.get("repository") or "").strip()
    evidence_id = _evidence_id(run_id, repository)
    existing = active_store.get("evidence_items", evidence_id)
    existing_bundle = existing.get("evidence") if isinstance(existing, dict) and isinstance(existing.get("evidence"), dict) else None
    if existing_bundle:
        reused = dict(existing_bundle)
        reused["idempotent_reuse"] = True
        return reused

    timeframe_days = max(30, min(int(context.get("timeframe_days") or DEFAULT_TIMEFRAME_DAYS), 365))
    github = client or GitHubAssessmentClient()
    repo_meta, repo_error = github.get_repo(repository)
    if repo_error or not repo_meta:
        bundle = {
            "status": "unavailable",
            "evidence_id": evidence_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": context.get("customer_id") or "default_customer",
            "project_id": context.get("project_id") or "default_project",
            "source": "github_api_read_only",
            "authorization_scope": context.get("authorization_scope") or "repository assessment only",
            "unavailable_data_notes": [_safe_api_note("Repository metadata", repo_error)],
            "idempotent_reuse": False,
            "human_review_required": True,
        }
        return _persist(bundle, active_store)

    since = _now() - timedelta(days=timeframe_days)
    since_iso = _iso(since)
    profile = fetch_repository_profile(github, repository, repo_meta)
    workflows, workflow_unavailable = fetch_workflows(github, repository)
    commits, commit_error = github.get_commits(repository, since_iso)
    pulls, pull_error = github.get_pulls(repository, since)
    workflow_runs, runs_error = github.get_workflow_runs(repository, since_iso)
    files = profile.get("files") if isinstance(profile.get("files"), dict) else {}
    file_scan = scan_files(files)

    unavailable = _safe_notes("Repository file-profile evidence", list(profile.get("unavailable") or []))
    unavailable.extend(_safe_notes("Workflow file evidence", list(workflow_unavailable or [])))
    for label, error in (("Commit history", commit_error), ("Pull-request history", pull_error), ("Workflow-run history", runs_error)):
        if error:
            unavailable.append(_safe_api_note(label, error))

    merged = sum(1 for item in pulls if item.get("merged_at"))
    open_count = sum(1 for item in pulls if item.get("state") == "open")
    bundle = {
        "status": "attached",
        "evidence_id": evidence_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "source": "github_api_read_only",
        "authorization_scope": context.get("authorization_scope") or "repository assessment only",
        "timeframe_days": timeframe_days,
        **_repository_summary(repo_meta, profile, files),
        "activity_evidence": {
            "commits_returned": len(commits),
            "pull_requests_returned": len(pulls),
            "merged_pull_requests": merged,
            "open_pull_requests": open_count,
            "sample_commits": _sample_commits(commits),
            "sample_pull_requests": _sample_pulls(pulls),
        },
        "workflow_evidence": _workflow_summary(workflows, workflow_runs),
        "code_signal_evidence": {
            "todo_fixme_security_notes": len(file_scan.get("todos") or []),
            "risk_pattern_hits": len(file_scan.get("risks") or []),
            "potential_secret_pattern_hits": len(file_scan.get("secrets") or []),
            "test_files_profiled": len(file_scan.get("test_paths") or []),
            "documentation_files_profiled": len(file_scan.get("docs") or []),
        },
        "unavailable_data_notes": sorted({note for note in unavailable if note}),
        "retention_note": "Only summarized repository evidence is retained in this record; source-file contents and credentials are not stored here.",
        "idempotent_reuse": False,
        "human_review_required": True,
    }
    return _persist(bundle, active_store)
