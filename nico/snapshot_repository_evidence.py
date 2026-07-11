from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from nico.full_assessment_ci_evidence import collect_ci_runtime_evidence
from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from nico.hosted_assessment import (
    DEPENDENCY_MANIFEST_NAMES,
    KNOWN_FILE_PATHS,
    LOCKFILE_NAMES,
    MAX_FILE_BYTES,
    MAX_TEXT_FILES,
    GitHubAssessmentClient,
    collect_dependencies,
    scan_files,
    should_fetch_path,
)
from nico.storage import STORE, StorageAdapter

DEFAULT_TIMEFRAME_DAYS = 180
DEPLOYMENT_NAMES = {"Dockerfile", "Procfile", "render.yaml", "railway.json", "railway.toml", "fly.toml", "vercel.json"}
WORKFLOW_COMMANDS = ["pytest", "npm test", "npm run lint", "npm run build", "next build", "eslint", "mypy", "ruff", "semgrep", "bandit"]


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _short(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _evidence_id(run_id: str, repository: str, snapshot_id: str) -> str:
    material = f"snapshot-repository-evidence|{run_id}|{repository}|{snapshot_id}".encode("utf-8")
    return f"evidence_snapshot_repo_{hashlib.sha256(material).hexdigest()[:20]}"


def _complexity_id(run_id: str, repository: str, snapshot_id: str) -> str:
    material = f"snapshot-complexity-evidence|{run_id}|{repository}|{snapshot_id}".encode("utf-8")
    return f"evidence_snapshot_complexity_{hashlib.sha256(material).hexdigest()[:20]}"


def _safe_api_note(label: str, error: str | None) -> str:
    lowered = str(error or "").lower()
    if "401" in lowered or "403" in lowered:
        return f"{label} was unavailable because the GitHub credential or installation lacks required read access."
    if "404" in lowered:
        return f"{label} was unavailable through the authorized GitHub API scope."
    if "429" in lowered or "rate" in lowered:
        return f"{label} was unavailable because the GitHub API rate limit was reached."
    return f"{label} was unavailable through the GitHub API."


def _get_json(client: Any, repository: str, path: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
    get_json = getattr(client, "get_json", None)
    repo_url = getattr(client, "repo_url", None)
    if not callable(get_json) or not callable(repo_url):
        return None, "GitHub JSON lookup is unavailable."
    return get_json(repo_url(repository, path), params)


def _contents_at_ref(client: Any, repository: str, path: str, ref: str) -> tuple[Any | None, str | None]:
    suffix = f"/contents/{quote(path, safe='/')}" if path else "/contents"
    return _get_json(client, repository, suffix, {"ref": ref})


def _tree_at_snapshot(client: Any, repository: str, tree_sha: str, commit_sha: str) -> tuple[list[dict[str, Any]], str | None]:
    ref = tree_sha or commit_sha
    value, error = _get_json(client, repository, f"/git/trees/{quote(ref, safe='')}", {"recursive": "1"})
    if error:
        return [], error
    if isinstance(value, dict) and isinstance(value.get("tree"), list):
        return [item for item in value["tree"] if isinstance(item, dict)], None
    return [], "Git tree was unavailable or not a list."


def _text_at_ref(client: Any, repository: str, path: str, ref: str) -> tuple[str | None, str | None]:
    import base64

    value, error = _contents_at_ref(client, repository, path, ref)
    if error:
        return None, error
    if not isinstance(value, dict) or value.get("type") != "file":
        return None, f"{path} is not a file at the captured commit."
    if int(value.get("size") or 0) > MAX_FILE_BYTES:
        return None, f"{path} is larger than the hosted text-inspection limit."
    try:
        return base64.b64decode(value.get("content") or "").decode("utf-8", errors="replace"), None
    except Exception:
        return None, f"{path} could not be decoded at the captured commit."


def _snapshot_profile(client: Any, repository: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    commit_sha = str(snapshot.get("commit_sha") or "")
    tree_sha = str(snapshot.get("tree_sha") or "")
    tree, tree_error = _tree_at_snapshot(client, repository, tree_sha, commit_sha)
    root, root_error = _contents_at_ref(client, repository, "", commit_sha)
    root_items = [str(item.get("name") or "") for item in root if isinstance(item, dict)] if isinstance(root, list) else []
    unavailable: list[str] = []
    if tree_error:
        unavailable.append(_safe_api_note("Captured-commit recursive file tree", tree_error))
    if root_error:
        unavailable.append(_safe_api_note("Captured-commit root listing", root_error))

    blobs = [item for item in tree if item.get("type") == "blob" and item.get("path")]
    path_sizes = {str(item.get("path")): int(item.get("size") or 0) for item in blobs}
    tree_paths = list(path_sizes)
    candidates = [path for path in KNOWN_FILE_PATHS if path in path_sizes]
    candidates.extend(
        path
        for path in tree_paths
        if path not in candidates and should_fetch_path(path, path_sizes.get(path))
    )
    files: dict[str, str] = {}
    for path in candidates[:MAX_TEXT_FILES]:
        text, error = _text_at_ref(client, repository, path, commit_sha)
        if text is not None:
            files[path] = text
        elif path in KNOWN_FILE_PATHS:
            unavailable.append(_safe_api_note(f"Captured-commit file {path}", error))
    return {
        "files": files,
        "tree_paths": tree_paths,
        "root_items": root_items,
        "unavailable": sorted(set(unavailable)),
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
    }


def _snapshot_workflows(client: Any, repository: str, snapshot: dict[str, Any], profile: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    commit_sha = str(snapshot.get("commit_sha") or "")
    paths = [path for path in profile.get("tree_paths") or [] if str(path).startswith(".github/workflows/") and str(path).endswith((".yml", ".yaml"))]
    workflows: dict[str, str] = {}
    unavailable: list[str] = []
    for path in paths:
        text, error = _text_at_ref(client, repository, str(path), commit_sha)
        if text is None:
            unavailable.append(_safe_api_note(f"Captured-commit workflow {path}", error))
        else:
            workflows[str(path)] = text
    if not paths:
        unavailable.append("No workflow files were present in the captured repository snapshot.")
    return workflows, unavailable


def _sample_commits(commits: list[dict[str, Any]], captured_at: datetime) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for item in commits:
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        date = _parse_iso(author.get("date"))
        if date and date > captured_at:
            continue
        samples.append({"sha": str(item.get("sha") or "")[:12], "date": author.get("date") or "", "message": _short(commit.get("message"), 160)})
        if len(samples) >= 10:
            break
    return samples


def _sample_pulls(pulls: list[dict[str, Any]], captured_at: datetime) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for item in pulls:
        updated = _parse_iso(item.get("updated_at"))
        if updated and updated > captured_at:
            continue
        samples.append(
            {
                "number": item.get("number"),
                "state": item.get("state") or "unknown",
                "merged": bool(item.get("merged_at")),
                "updated_at": item.get("updated_at") or "",
                "title": _short(item.get("title"), 160),
            }
        )
        if len(samples) >= 10:
            break
    return samples


def _workflow_summary(workflows: dict[str, str], runs: list[dict[str, Any]], ci_runtime: dict[str, Any], snapshot_sha: str) -> dict[str, Any]:
    combined = "\n".join(workflows.values()).lower()
    terminal = [item for item in runs if item.get("conclusion")]
    success = sum(1 for item in terminal if item.get("conclusion") == "success")
    non_success = sum(1 for item in terminal if item.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"})
    matching_snapshot_runs = sum(1 for item in runs if str(item.get("head_sha") or "").lower() == snapshot_sha.lower())
    jobs = ci_runtime.get("job_evidence") if isinstance(ci_runtime.get("job_evidence"), dict) else {}
    deployments = ci_runtime.get("deployment_evidence") if isinstance(ci_runtime.get("deployment_evidence"), dict) else {}
    controls = ci_runtime.get("configuration_controls") if isinstance(ci_runtime.get("configuration_controls"), dict) else {}
    return {
        "workflow_files": sorted(workflows),
        "workflow_file_count": len(workflows),
        "workflow_configuration_snapshot_sha": snapshot_sha,
        "workflow_run_count": len(runs),
        "successful_runs": success,
        "non_success_runs": non_success,
        "runs_matching_snapshot_sha": matching_snapshot_runs,
        "commands_detected": [command for command in WORKFLOW_COMMANDS if command in combined],
        "explicit_permissions_present": "permissions:" in combined,
        "secret_references_present": "secrets." in combined,
        "runtime_evidence_status": ci_runtime.get("status") or "unavailable",
        "configuration_controls": controls,
        "job_evidence": jobs,
        "deployment_evidence": deployments,
        "jobs_observed": int(jobs.get("jobs_observed") or 0),
        "successful_jobs": int(jobs.get("successful_jobs") or 0),
        "non_success_jobs": int(jobs.get("non_success_jobs") or 0),
        "job_success_rate": jobs.get("job_success_rate"),
        "average_job_duration_seconds": jobs.get("average_job_duration_seconds"),
        "median_job_duration_seconds": jobs.get("median_job_duration_seconds"),
        "deployments_observed": int(deployments.get("deployments_observed") or 0),
        "successful_deployments": int(deployments.get("successful_deployments") or 0),
        "non_success_deployments": int(deployments.get("non_success_deployments") or 0),
        "ci_runtime_guardrail": "Workflow configuration is bound to the captured commit. Run, job, and deployment evidence is historical operational evidence observed through the capture time and may include other commits.",
    }


def _persist(bundle: dict[str, Any], store: StorageAdapter, filename: str) -> dict[str, Any]:
    encoded = json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    store.put(
        "evidence_items",
        str(bundle["evidence_id"]),
        {
            "evidence_id": bundle["evidence_id"],
            "customer_id": bundle.get("customer_id") or "default_customer",
            "project_id": bundle.get("project_id") or "default_project",
            "run_id": bundle.get("run_id") or "",
            "filename": filename,
            "content_type": "application/json",
            "size_bytes": len(encoded),
            "source": bundle.get("source") or "github_api_read_only",
            "repository": bundle.get("repository") or "",
            "evidence": bundle,
        },
    )
    return bundle


def collect_snapshot_repository_evidence(
    context: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    client: GitHubAssessmentClient | None = None,
    store: StorageAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect code evidence from one commit and label operational history separately."""

    active_store = _store(store)
    run_id = str(context.get("run_id") or "")
    repository = str(context.get("repository") or "")
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    evidence_id = _evidence_id(run_id, repository, snapshot_id)
    complexity_id = _complexity_id(run_id, repository, snapshot_id)
    existing = active_store.get("evidence_items", evidence_id)
    existing_complexity = active_store.get("evidence_items", complexity_id)
    if isinstance(existing, dict) and isinstance(existing.get("evidence"), dict) and isinstance(existing_complexity, dict) and isinstance(existing_complexity.get("evidence"), dict):
        bundle = dict(existing["evidence"])
        complexity = dict(existing_complexity["evidence"])
        bundle["idempotent_reuse"] = True
        complexity["idempotent_reuse"] = True
        return bundle, complexity

    required_snapshot = bool(
        snapshot.get("status") == "attached"
        and snapshot.get("run_id") == run_id
        and snapshot.get("repository") == repository
        and snapshot.get("commit_sha")
    )
    if not required_snapshot:
        unavailable = {
            "status": "unavailable",
            "evidence_id": evidence_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": context.get("customer_id") or "default_customer",
            "project_id": context.get("project_id") or "default_project",
            "snapshot_id": snapshot_id,
            "source": "github_api_read_only",
            "unavailable_data_notes": ["Snapshot-bound repository evidence requires an attached snapshot with matching run and repository identity."],
            "idempotent_reuse": False,
            "human_review_required": True,
        }
        complexity = {
            **unavailable,
            "evidence_id": complexity_id,
            "source": "github_api_snapshot_bound_complexity",
        }
        return unavailable, complexity

    github = client or GitHubAssessmentClient()
    captured_at = _parse_iso(snapshot.get("captured_at")) or datetime.now(timezone.utc)
    timeframe_days = max(30, min(int(context.get("timeframe_days") or DEFAULT_TIMEFRAME_DAYS), 365))
    since = captured_at - timedelta(days=timeframe_days)
    profile = _snapshot_profile(github, repository, snapshot)
    files = profile.get("files") if isinstance(profile.get("files"), dict) else {}
    workflows, workflow_unavailable = _snapshot_workflows(github, repository, snapshot, profile)

    commits, commit_error = github.get_commits(repository, _iso(since))
    pulls, pull_error = github.get_pulls(repository, since)
    workflow_runs, run_error = github.get_workflow_runs(repository, _iso(since))
    workflow_runs = [item for item in workflow_runs if not _parse_iso(item.get("created_at")) or _parse_iso(item.get("created_at")) <= captured_at]
    ci_runtime = collect_ci_runtime_evidence(github, repository, workflows, workflow_runs)
    file_scan = scan_files(files)
    dependencies = collect_dependencies(files)
    tree_paths = list(profile.get("tree_paths") or [])
    source_paths = [path for path in tree_paths if str(path).endswith((".py", ".ts", ".tsx", ".js", ".jsx")) and not str(path).startswith("tests/") and "test" not in str(path).rsplit("/", 1)[-1].lower()]
    test_paths = [path for path in tree_paths if "test" in str(path).lower()]
    doc_paths = [path for path in tree_paths if str(path).lower().endswith(".md") or str(path).startswith("docs/")]
    deployment = [path for path in tree_paths if str(path).rsplit("/", 1)[-1] in DEPLOYMENT_NAMES]
    manifests = [path for path in files if str(path).rsplit("/", 1)[-1] in DEPENDENCY_MANIFEST_NAMES]
    lockfiles = [path for path in files if str(path).rsplit("/", 1)[-1] in LOCKFILE_NAMES]
    unavailable_notes = list(profile.get("unavailable") or []) + workflow_unavailable
    for label, error in (("Commit history", commit_error), ("Pull-request history", pull_error), ("Workflow-run history", run_error)):
        if error:
            unavailable_notes.append(_safe_api_note(label, error))
    unavailable_notes.extend(str(item) for item in ci_runtime.get("unavailable_data_notes") or [])

    sample_commits = _sample_commits(commits, captured_at)
    sample_pulls = _sample_pulls(pulls, captured_at)
    bundle = {
        "status": "attached",
        "evidence_id": evidence_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "source": "github_api_snapshot_bound_read_only",
        "authorization_scope": context.get("authorization_scope") or "repository assessment only",
        "timeframe_days": timeframe_days,
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        "snapshot_tree_sha": snapshot.get("tree_sha") or "",
        "snapshot_captured_at": snapshot.get("captured_at") or "",
        "code_evidence_scope": "All file, manifest, workflow-configuration, code-signal, and complexity evidence in this bundle is read from the exact captured commit.",
        "operational_evidence_scope": "Commit, PR, workflow-run, job, and deployment history is time-window evidence observed through snapshot capture time and is not represented as code from the exact commit unless explicitly matched by SHA.",
        "repository_metadata": {
            "full_name": repository,
            "default_branch": snapshot.get("default_branch") or "",
            "visibility": snapshot.get("repository_visibility") or "unknown",
            "pushed_at": snapshot.get("repository_pushed_at") or "",
            "commit_sha": snapshot.get("commit_sha") or "",
            "tree_sha": snapshot.get("tree_sha") or "",
        },
        "file_evidence": {
            "files_profiled": len(files),
            "tree_paths_seen": len(tree_paths),
            "sampled_paths": sorted(files)[:40],
            "top_level_items": sorted(profile.get("root_items") or [])[:40],
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        },
        "architecture_evidence": {
            "source_file_count": len(source_paths),
            "test_path_count": len(test_paths),
            "documentation_path_count": len(doc_paths),
            "deployment_manifests": sorted(deployment)[:20],
            "top_level_directories": sorted(item for item in profile.get("root_items") or [] if "." not in str(item))[:30],
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        },
        "dependency_evidence": {
            "manifest_paths": sorted(manifests),
            "lockfile_paths": sorted(lockfiles),
            "dependency_entries": len(dependencies),
            "ecosystems": sorted({str(item.get("ecosystem") or "unknown") for item in dependencies}),
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        },
        "activity_evidence": {
            "status": "time_window_operational_evidence",
            "captured_through": _iso(captured_at),
            "commits_returned": len(sample_commits),
            "pull_requests_returned": len(sample_pulls),
            "merged_pull_requests": sum(1 for item in sample_pulls if item.get("merged")),
            "open_pull_requests": sum(1 for item in sample_pulls if item.get("state") == "open"),
            "sample_commits": sample_commits,
            "sample_pull_requests": sample_pulls,
        },
        "workflow_evidence": _workflow_summary(workflows, workflow_runs, ci_runtime, str(snapshot.get("commit_sha") or "")),
        "code_signal_evidence": {
            "todo_fixme_security_notes": len(file_scan.get("todos") or []),
            "risk_pattern_hits": len(file_scan.get("risks") or []),
            "potential_secret_pattern_hits": len(file_scan.get("secrets") or []),
            "test_files_profiled": len(file_scan.get("test_paths") or []),
            "documentation_files_profiled": len(file_scan.get("docs") or []),
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        },
        "unavailable_data_notes": sorted({str(note) for note in unavailable_notes if str(note).strip()}),
        "retention_note": "Only summarized repository evidence and bounded sampled file content analysis are retained; credentials and raw CI logs are not retained.",
        "idempotent_reuse": False,
        "human_review_required": True,
    }

    measured = collect_complexity_evidence(files)
    complexity = {
        **measured,
        "evidence_id": complexity_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "source": "github_api_snapshot_bound_complexity",
        "authorization_scope": context.get("authorization_scope") or "repository assessment only",
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot.get("commit_sha") or "",
        "snapshot_tree_sha": snapshot.get("tree_sha") or "",
        "profiled_file_count": len(files),
        "profile_unavailable_count": len(profile.get("unavailable") or []),
        "idempotent_reuse": False,
        "human_review_required": True,
        "guardrail": "Complexity measurements cover only readable sampled source files from the exact captured commit.",
    }
    notes = list(complexity.get("unavailable_data_notes") or [])
    if profile.get("unavailable"):
        notes.append(f"{len(profile.get('unavailable') or [])} captured-commit profile item(s) were unavailable; complexity coverage is limited to readable sampled files.")
    complexity["unavailable_data_notes"] = sorted({str(note) for note in notes if str(note).strip()})

    _persist(bundle, active_store, "snapshot-repository-evidence.json")
    _persist(complexity, active_store, "snapshot-complexity-evidence.json")
    active_store.audit(
        "assessment.snapshot_repository_evidence_collected",
        {
            "run_id": run_id,
            "repository": repository,
            "snapshot_id": snapshot_id,
            "snapshot_commit_sha": snapshot.get("commit_sha") or "",
            "files_profiled": len(files),
            "workflow_files": len(workflows),
            "complexity_files": complexity.get("files_analyzed") or 0,
        },
        customer_id=context.get("customer_id") or "default_customer",
        project_id=context.get("project_id") or "default_project",
    )
    return bundle, complexity
