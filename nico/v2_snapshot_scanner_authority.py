from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from nico import scanner_tool_runners
from nico import snapshot_scanner_worker
from nico.scanner_evidence_pipeline_v1 import (
    DEFAULT_RAW_ROOT,
    REQUIRED_EVIDENCE_TOOLS,
    _run_problem_tool,
    _target_repository,
    prepare_project_commands,
    redact_payload,
)
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace, run_command

VERSION = "nico.v2.snapshot-scanner-authority.v2"
_TOOL_MARKER = "__nico_v2_snapshot_tool_authority_v2__"
_CLONE_MARKER = "__nico_v2_full_history_clone_v2__"
_PREPARATION_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _commit_sha(workspace: WorkerWorkspace) -> str:
    try:
        result = run_command(
            ("git", "rev-parse", "HEAD"),
            cwd=workspace.repo_dir,
            limits=__import__("nico.worker_execution", fromlist=["WorkerLimits"]).WorkerLimits(30, 4000),
        )
    except Exception:
        return ""
    value = (result.stdout or "").strip().casefold()
    return value if len(value) == 40 else ""


def _preparation(workspace: WorkerWorkspace, runner: Callable[..., WorkerCommandResult]) -> Any:
    key = str(workspace.root)
    with _CACHE_LOCK:
        cached = _PREPARATION_CACHE.get(key)
    if cached is not None:
        return cached
    prepared = prepare_project_commands(workspace, runner=runner)
    with _CACHE_LOCK:
        _PREPARATION_CACHE[key] = prepared
    return prepared


def _persist_raw_blob(
    payload: dict[str, Any],
    blob: dict[str, Any],
    *,
    workspace: WorkerWorkspace,
) -> None:
    compressed = bytes.fromhex(str(blob.get("gzip_hex") or ""))
    if not compressed or _sha256(compressed) != str(blob.get("gzip_sha256") or ""):
        raise ValueError("compressed scanner artifact checksum mismatch")
    raw = gzip.decompress(compressed)
    if _sha256(raw) != str(blob.get("sha256") or ""):
        raise ValueError("scanner artifact checksum mismatch")

    repository = _target_repository(workspace)
    commit_sha = _commit_sha(workspace) or "unknown"
    run_key = _sha256(str(workspace.root).encode("utf-8"))[:20]
    repository_key = _sha256(repository.encode("utf-8"))[:16]
    destination = Path(DEFAULT_RAW_ROOT) / repository_key / commit_sha / run_key
    destination.mkdir(parents=True, exist_ok=True)
    filename = str(blob.get("filename") or f"{payload.get('tool')}.raw.gz").replace("/", "_")
    path = destination / filename
    path.write_bytes(compressed)
    path.chmod(0o600)
    storage_key = str(path.relative_to(Path(DEFAULT_RAW_ROOT)))
    payload["raw_artifact"] = {
        "storage_key": storage_key,
        "filename": filename,
        "sha256": blob.get("sha256"),
        "gzip_sha256": blob.get("gzip_sha256"),
        "raw_format": blob.get("raw_format"),
        "retained_bytes": blob.get("retained_bytes"),
        "gzip_bytes": blob.get("gzip_bytes"),
        "redacted": True,
    }
    payload["raw_artifact_retention_complete"] = True
    payload["raw_artifact_sha256"] = blob.get("sha256")

    manifest = destination / "manifest.json"
    existing: dict[str, Any] = {}
    if manifest.exists():
        try:
            decoded = json.loads(manifest.read_text(encoding="utf-8"))
            existing = decoded if isinstance(decoded, dict) else {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    artifacts = existing.get("artifacts") if isinstance(existing.get("artifacts"), dict) else {}
    artifacts[str(payload.get("tool") or "unknown")] = payload["raw_artifact"]
    manifest_payload = {
        "schema": "nico.v2.snapshot-scanner-artifacts.v2",
        "repository": repository,
        "commit_sha": commit_sha,
        "run_key": run_key,
        "pipeline_version": VERSION,
        "artifacts": dict(sorted(artifacts.items())),
    }
    manifest.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
    manifest.chmod(0o600)
    payload["raw_artifact_manifest_storage_key"] = str(manifest.relative_to(Path(DEFAULT_RAW_ROOT)))


def _raw_json(blob: Mapping[str, Any]) -> Any:
    try:
        compressed = bytes.fromhex(str(blob.get("gzip_hex") or ""))
        raw = gzip.decompress(compressed)
        if _sha256(raw) != str(blob.get("sha256") or ""):
            return None
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, OSError, gzip.BadGzipFile, json.JSONDecodeError):
        return None


def _package_context(value: Mapping[str, Any], inherited: Mapping[str, Any]) -> dict[str, Any]:
    context = deepcopy(dict(inherited))
    package = value.get("package")
    if isinstance(package, Mapping):
        if _text(package.get("name")):
            context["package"] = _text(package.get("name"))
        if _text(package.get("ecosystem")):
            context["ecosystem"] = _text(package.get("ecosystem"))
        if _text(package.get("version")):
            context["installed_version"] = _text(package.get("version"))
    elif _text(package):
        context["package"] = _text(package)
    for key, target in (
        ("name", "package"),
        ("version", "installed_version"),
        ("installed_version", "installed_version"),
        ("ecosystem", "ecosystem"),
        ("source", "dependency_path"),
        ("path", "dependency_path"),
        ("manifest", "dependency_path"),
        ("lockfile", "dependency_path"),
    ):
        if _text(value.get(key)) and not _text(context.get(target)):
            context[target] = _text(value.get(key))
    return context


def _walk_osv(value: Any, context: Mapping[str, Any], output: list[dict[str, Any]]) -> None:
    if isinstance(value, Mapping):
        local = _package_context(value, context)
        for key, child in value.items():
            if key in {"vulnerabilities", "vulns"} and isinstance(child, list):
                for raw in child:
                    if not isinstance(raw, Mapping):
                        continue
                    item = deepcopy(dict(raw))
                    item.setdefault("package", local.get("package"))
                    item.setdefault("installed_version", local.get("installed_version"))
                    item.setdefault("ecosystem", local.get("ecosystem"))
                    item.setdefault("dependency_path", local.get("dependency_path"))
                    output.append(item)
            else:
                _walk_osv(child, local, output)
    elif isinstance(value, list):
        for child in value:
            _walk_osv(child, context, output)


def _enrich_osv_findings(payload: dict[str, Any], blob: Mapping[str, Any] | None) -> None:
    if _text(payload.get("tool")) != "osv-scanner" or not isinstance(blob, Mapping):
        return
    raw = _raw_json(blob)
    if raw is None:
        payload["dependency_context_enrichment"] = {
            "status": "review_required",
            "reason": "retained OSV JSON could not be decoded for package-context enrichment",
        }
        return
    enriched: list[dict[str, Any]] = []
    _walk_osv(raw, {}, enriched)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in enriched:
        marker = json.dumps(item, sort_keys=True, default=str, separators=(",", ":"))
        if marker in seen:
            continue
        seen.add(marker)
        selected.append(item)
    if selected:
        payload["findings"] = selected
        payload["findings_count"] = len(selected)
    payload["dependency_context_enrichment"] = {
        "status": "complete" if selected else "review_required",
        "raw_vulnerability_count": len(selected),
        "package_context_retained": all(_text(item.get("package")) for item in selected) if selected else False,
        "installed_version_retained": all(_text(item.get("installed_version")) for item in selected) if selected else False,
        "advisory_identity_retained": all(_text(item.get("id") or (item.get("aliases") or [""])[0]) for item in selected) if selected else False,
    }


def canonical_snapshot_tool_runner(
    spec: scanner_tool_runners.ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
    preparation: Any = None,
) -> dict[str, Any]:
    if spec.name not in REQUIRED_EVIDENCE_TOOLS:
        previous = getattr(canonical_snapshot_tool_runner, "_nico_previous")
        return previous(spec, workspace, runner=runner, preparation=preparation)

    prepared = preparation
    if spec.name in {"eslint", "typescript"} and prepared is None:
        prepared = _preparation(workspace, runner)
    payload = _run_problem_tool(spec, workspace, runner, prepared)
    if not isinstance(payload, dict):
        raise TypeError(f"canonical scanner payload must be an object: {spec.name}")
    blob = payload.get("_raw_artifact_blob")
    _enrich_osv_findings(payload, blob if isinstance(blob, Mapping) else None)
    blob = payload.pop("_raw_artifact_blob", None)
    if isinstance(blob, dict):
        try:
            _persist_raw_blob(payload, blob, workspace=workspace)
        except Exception as exc:
            payload["status"] = "failed"
            payload["verified_for_this_report"] = False
            payload["raw_artifact_retention_complete"] = False
            payload["reason"] = f"raw scanner artifact retention failed: {type(exc).__name__}: {exc}"
            payload["failure_or_unavailable_reason"] = payload["reason"]
    else:
        payload["raw_artifact_retention_complete"] = False

    commit_sha = _commit_sha(workspace)
    payload["scanner_name"] = spec.name
    payload["commit_sha"] = commit_sha
    payload["snapshot_commit_sha"] = commit_sha
    payload["exact_commit_match"] = bool(commit_sha)
    payload["exit_code"] = payload.get("returncode")
    completed = payload.get("status") == "completed" and payload.get("raw_artifact_retention_complete") is True
    payload["completed"] = completed
    payload["verified"] = completed and payload.get("verified_for_this_report") is True
    payload["verified_complete"] = payload["verified"]
    if not completed and not payload.get("failure_reason"):
        payload["failure_reason"] = str(
            payload.get("failure_or_unavailable_reason")
            or payload.get("reason")
            or "scanner did not retain a complete exact-SHA artifact"
        )
    safe = redact_payload(payload)
    safe["artifact_hash"] = _sha256(
        json.dumps(
            {key: value for key, value in safe.items() if key != "artifact_hash"},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    return safe


def _git(repo_path: Path, env: Mapping[str, str], *args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(env),
        check=False,
    )


def _config(repo_path: Path, env: Mapping[str, str], key: str) -> str:
    result = _git(repo_path, env, "config", "--get", key, timeout=30)
    return _text(result.stdout) if result.returncode == 0 else ""


def _materialize_git_history(repo_path: Path, env: Mapping[str, str], notes: list[str]) -> tuple[list[str], bool]:
    shallow = _git(repo_path, env, "rev-parse", "--is-shallow-repository", timeout=30)
    if shallow.returncode != 0:
        return [*notes, "Git repository depth could not be verified for history-aware secret scanning."], False
    if _text(shallow.stdout).casefold() == "true":
        unshallow = _git(repo_path, env, "fetch", "--unshallow", "--tags", "origin", timeout=600)
        if unshallow.returncode != 0:
            return [*notes, f"Full git history could not be restored: {_text(unshallow.stderr)[:500]}"], False

    partial_keys = (
        "remote.origin.promisor",
        "remote.origin.partialclonefilter",
        "extensions.partialClone",
    )
    partial = any(_config(repo_path, env, key) for key in partial_keys)
    if partial:
        for key in partial_keys:
            _git(repo_path, env, "config", "--unset-all", key, timeout=30)
        refetch = _git(
            repo_path,
            env,
            "fetch",
            "--refetch",
            "--tags",
            "--prune",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
            timeout=900,
        )
        if refetch.returncode != 0:
            fallback = _git(
                repo_path,
                env,
                "fetch",
                "--tags",
                "--prune",
                "origin",
                "+refs/heads/*:refs/remotes/origin/*",
                timeout=900,
            )
            if fallback.returncode != 0:
                return [*notes, f"Partial clone objects could not be materialized: {_text(fallback.stderr or refetch.stderr)[:500]}"], False

    repack = _git(repo_path, env, "repack", "-a", "-d", timeout=900)
    if repack.returncode != 0:
        return [*notes, f"Full-object repository repack failed: {_text(repack.stderr)[:500]}"], False
    verify_depth = _git(repo_path, env, "rev-parse", "--is-shallow-repository", timeout=30)
    fsck = _git(repo_path, env, "fsck", "--full", "--no-dangling", timeout=900)
    valid = (
        verify_depth.returncode == 0
        and _text(verify_depth.stdout).casefold() == "false"
        and fsck.returncode == 0
        and not any(_config(repo_path, env, key) for key in partial_keys)
    )
    if not valid:
        return [*notes, f"Full git object verification failed: {_text(fsck.stderr or fsck.stdout)[:500]}"], False
    return [*notes, "Full git history and object store were materialized and verified for history-aware secret scanning."], True


def full_history_snapshot_clone(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: dict[str, str],
) -> tuple[Path | None, str, list[str]]:
    previous = getattr(full_history_snapshot_clone, "_nico_previous")
    repo_path, actual_sha, notes = previous(repository, commit_sha, workspace, env)
    if repo_path is None or os.getenv("NICO_ENABLE_FULL_HISTORY_SECRET_SCAN", "false").casefold() != "true":
        return repo_path, actual_sha, notes
    try:
        notes, materialized = _materialize_git_history(repo_path, env, list(notes))
        verified_sha = _git(repo_path, env, "rev-parse", "HEAD", timeout=30)
        observed = _text(verified_sha.stdout).casefold() if verified_sha.returncode == 0 else ""
        if observed != _text(commit_sha).casefold():
            notes = [*notes, "Full-history materialization changed or could not verify the assessed commit identity."]
        elif not materialized:
            notes = [*notes, "Gitleaks and TruffleHog must remain unverified until full object materialization succeeds."]
    except Exception as exc:
        notes = [*notes, f"Full-history object materialization failed safely: {type(exc).__name__}: {_text(exc)}"]
    return repo_path, actual_sha, notes


def install_v2_snapshot_scanner_authority() -> dict[str, Any]:
    current_tool = scanner_tool_runners.run_scanner_tool
    if not getattr(current_tool, _TOOL_MARKER, False):
        setattr(canonical_snapshot_tool_runner, "_nico_previous", current_tool)
        setattr(canonical_snapshot_tool_runner, _TOOL_MARKER, True)
        scanner_tool_runners.run_scanner_tool = canonical_snapshot_tool_runner

    current_clone = snapshot_scanner_worker.clone_repository_at_snapshot
    if not getattr(current_clone, _CLONE_MARKER, False):
        setattr(full_history_snapshot_clone, "_nico_previous", current_clone)
        setattr(full_history_snapshot_clone, _CLONE_MARKER, True)
        snapshot_scanner_worker.clone_repository_at_snapshot = full_history_snapshot_clone

    tool_bound = scanner_tool_runners.run_scanner_tool is canonical_snapshot_tool_runner
    clone_bound = snapshot_scanner_worker.clone_repository_at_snapshot is full_history_snapshot_clone
    return {
        "status": "installed" if tool_bound and clone_bound else "blocked",
        "version": VERSION,
        "bound": tool_bound and clone_bound,
        "snapshot_worker_uses_canonical_scanner_runner": tool_bound,
        "raw_artifacts_retained_before_workspace_deletion": tool_bound,
        "osv_package_context_retained": tool_bound,
        "returncode_and_exit_code_both_exposed": tool_bound,
        "exact_commit_identity_exposed": tool_bound,
        "full_history_restoration_bound": clone_bound,
        "partial_clone_objects_materialized": clone_bound,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonical_snapshot_tool_runner",
    "full_history_snapshot_clone",
    "install_v2_snapshot_scanner_authority",
]
