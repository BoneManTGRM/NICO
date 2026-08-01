from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from nico import scanner_evidence_pipeline_v1 as scanner_pipeline
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
from nico.scanner_result_truth_v1 import reconcile_scanner_payload
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace, run_command

VERSION = "nico.v2.snapshot-scanner-authority.v4"
_TOOL_MARKER = "__nico_v2_snapshot_tool_authority_v2__"
_CLONE_MARKER = "__nico_v2_full_history_clone_v2__"
_HISTORY_COMMAND_MARKER = "__nico_v2_exact_sha_history_commands_v1__"
_PREPARATION_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _force_option(command: tuple[str, ...], option: str, value: str) -> tuple[str, ...]:
    parts = list(command)
    if option in parts:
        index = parts.index(option)
        if index + 1 < len(parts):
            parts[index + 1] = value
        else:
            parts.append(value)
    else:
        parts.extend((option, value))
    return tuple(parts)


def _head_scoped_runner(
    tool_name: str,
    runner: Callable[..., WorkerCommandResult],
) -> Callable[..., WorkerCommandResult]:
    def scoped(command: tuple[str, ...], **kwargs: Any) -> WorkerCommandResult:
        immutable_command = tuple(command)
        if tool_name == "gitleaks":
            immutable_command = _force_option(immutable_command, "--log-opts", "HEAD")
        elif tool_name == "trufflehog":
            immutable_command = _force_option(immutable_command, "--branch", "HEAD")
        filtered = scanner_pipeline._runner_kwargs(runner, **kwargs)
        return runner(immutable_command, **filtered)

    return scoped


def _history_scoped_delegate(
    delegate: Callable[..., dict[str, Any]],
    tool_name: str,
) -> Callable[..., dict[str, Any]]:
    @wraps(delegate)
    def wrapped(
        spec: scanner_tool_runners.ScannerToolSpec,
        workspace: WorkerWorkspace,
        runner: Callable[..., WorkerCommandResult],
    ) -> dict[str, Any]:
        result = delegate(spec, workspace, _head_scoped_runner(tool_name, runner))
        if not isinstance(result, dict):
            return result
        output = dict(result)
        verified = bool(
            output.get("status") == "completed"
            and output.get("full_history_verified") is True
        )
        output.update(
            {
                "history_scope": "reachable_ancestry_at_assessed_commit",
                "history_depth_verified": verified,
                "immutable_head_selector": "HEAD",
                "deterministic_head_selector_applied": True,
                "descendant_refs_scanned": False,
            }
        )
        return output

    setattr(wrapped, _HISTORY_COMMAND_MARKER, tool_name)
    setattr(wrapped, "_nico_previous", delegate)
    return wrapped


def _install_history_command_scope() -> dict[str, bool]:
    installed: dict[str, bool] = {}
    for attribute, tool_name in (
        ("_run_gitleaks", "gitleaks"),
        ("_run_trufflehog", "trufflehog"),
    ):
        current = getattr(scanner_pipeline, attribute)
        if getattr(current, _HISTORY_COMMAND_MARKER, None) != tool_name:
            current = _history_scoped_delegate(current, tool_name)
            setattr(scanner_pipeline, attribute, current)
        installed[tool_name] = getattr(current, _HISTORY_COMMAND_MARKER, None) == tool_name
    return installed


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
        "schema": "nico.v2.snapshot-scanner-artifacts.v3",
        "repository": repository,
        "commit_sha": commit_sha,
        "run_key": run_key,
        "pipeline_version": VERSION,
        "artifacts": dict(sorted(artifacts.items())),
    }
    manifest.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
    manifest.chmod(0o600)
    payload["raw_artifact_manifest_storage_key"] = str(manifest.relative_to(Path(DEFAULT_RAW_ROOT)))


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

    # Enforce immutable HEAD selection at the final runner boundary. This remains
    # effective even when test or compatibility installers replace the named
    # scanner delegates while preserving the canonical snapshot authority.
    effective_runner = (
        _head_scoped_runner(spec.name, runner)
        if bool(spec.scans_git_history)
        else runner
    )
    payload = _run_problem_tool(spec, workspace, effective_runner, prepared)
    if not isinstance(payload, dict):
        raise TypeError(f"canonical scanner payload must be an object: {spec.name}")
    raw_blob = payload.get("_raw_artifact_blob")
    payload = reconcile_scanner_payload(spec.name, payload, raw_blob, workspace)
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
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )
        if shallow.returncode == 0 and (shallow.stdout or "").strip().casefold() == "true":
            unshallow = subprocess.run(
                ["git", "fetch", "--unshallow", "--no-tags", "origin", commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
                check=False,
            )
            if unshallow.returncode != 0:
                notes = [*notes, "Exact-commit reachable history could not be restored for history-aware secret scanning."]
        verify = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )
        if verify.returncode != 0 or (verify.stdout or "").strip().casefold() != "false":
            notes = [*notes, "Repository history remains shallow; Gitleaks and TruffleHog must remain unverified."]
    except Exception as exc:
        notes = [*notes, f"Exact-commit history preparation failed safely: {type(exc).__name__}."]
    return repo_path, actual_sha, notes


def install_v2_snapshot_scanner_authority() -> dict[str, Any]:
    current_tool = scanner_tool_runners.run_scanner_tool
    if not getattr(current_tool, _TOOL_MARKER, False):
        setattr(canonical_snapshot_tool_runner, "_nico_previous", current_tool)
        setattr(canonical_snapshot_tool_runner, _TOOL_MARKER, True)
        scanner_tool_runners.run_scanner_tool = canonical_snapshot_tool_runner

    history_scope = _install_history_command_scope()

    # The deterministic clone fetches the assessed commit and all ancestry reachable
    # from that commit without retaining branches, remotes, or tags. Replacing it with
    # the legacy unshallow wrapper would reintroduce mutable refs and same-SHA drift.
    from nico.scanner_determinism_v1 import clone_repository_at_snapshot as deterministic_clone

    snapshot_scanner_worker.clone_repository_at_snapshot = deterministic_clone

    tool_bound = bool(getattr(scanner_tool_runners.run_scanner_tool, _TOOL_MARKER, False))
    clone_bound = snapshot_scanner_worker.clone_repository_at_snapshot is deterministic_clone
    history_commands_bound = all(history_scope.values())
    bound = tool_bound and clone_bound and history_commands_bound
    return {
        "status": "installed" if bound else "blocked",
        "version": VERSION,
        "bound": bound,
        "snapshot_worker_uses_canonical_scanner_runner": tool_bound,
        "raw_artifacts_retained_before_workspace_deletion": tool_bound,
        "source_aware_scanner_projection_bound": tool_bound,
        "authoritative_osv_manifest_context_required": tool_bound,
        "example_secret_placeholders_nonblocking_only_when_verified": tool_bound,
        "returncode_and_exit_code_both_exposed": tool_bound,
        "exact_commit_identity_exposed": tool_bound,
        "full_history_restoration_bound": clone_bound,
        "exact_commit_reachable_ancestry_bound": clone_bound,
        "mutable_branch_remote_and_tag_refs_excluded": clone_bound,
        "history_scanners_bound_to_head": history_commands_bound,
        "history_command_scope": history_scope,
        "final_runner_head_scope_bound": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonical_snapshot_tool_runner",
    "full_history_snapshot_clone",
    "install_v2_snapshot_scanner_authority",
]
