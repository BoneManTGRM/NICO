from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from nico import scanner_tool_runners, snapshot_scanner_worker
from nico.scanner_evidence_pipeline_v1 import DEFAULT_RAW_ROOT, redact_payload
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace, run_command

VERSION = "nico.v2.scanner-evidence-completion.v1"
_TOOL_MARKER = "__nico_v2_scanner_evidence_completion_v1__"
_CLONE_MARKER = "__nico_v2_scanner_object_materialization_v1__"
_PARTIAL_CLONE_KEYS = (
    "remote.origin.promisor",
    "remote.origin.partialclonefilter",
    "extensions.partialClone",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(
    repository: Path,
    environment: Mapping[str, str],
    *arguments: str,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(environment),
        check=False,
    )


def _config(repository: Path, environment: Mapping[str, str], key: str) -> str:
    result = _git(repository, environment, "config", "--get", key, timeout=30)
    return _text(result.stdout) if result.returncode == 0 else ""


def _fixed_versions(vulnerability: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    direct = vulnerability.get("fixed_versions") or vulnerability.get("fixed_version")
    if isinstance(direct, str) and _text(direct):
        values.append(_text(direct))
    elif isinstance(direct, (list, tuple)):
        values.extend(_text(item) for item in direct if _text(item))
    affected = vulnerability.get("affected")
    if isinstance(affected, list):
        for affected_item in affected:
            if not isinstance(affected_item, Mapping):
                continue
            for range_item in affected_item.get("ranges") or []:
                if not isinstance(range_item, Mapping):
                    continue
                for event in range_item.get("events") or []:
                    if isinstance(event, Mapping) and _text(event.get("fixed")):
                        values.append(_text(event.get("fixed")))
    return list(dict.fromkeys(values))


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
    for source, target in (
        ("name", "package"),
        ("version", "installed_version"),
        ("installed_version", "installed_version"),
        ("ecosystem", "ecosystem"),
        ("source", "dependency_path"),
        ("path", "dependency_path"),
        ("manifest", "dependency_path"),
        ("lockfile", "dependency_path"),
    ):
        if _text(value.get(source)) and not _text(context.get(target)):
            context[target] = _text(value.get(source))
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
                    fixed = _fixed_versions(item)
                    if fixed:
                        item["fixed_versions"] = fixed
                        item.setdefault("fixed_version", fixed[0])
                    output.append(item)
            else:
                _walk_osv(child, local, output)
    elif isinstance(value, list):
        for child in value:
            _walk_osv(child, context, output)


def _retained_raw_json(payload: Mapping[str, Any]) -> Any:
    artifact = payload.get("raw_artifact")
    if not isinstance(artifact, Mapping):
        return None
    storage_key = _text(artifact.get("storage_key"))
    if not storage_key:
        return None
    root = Path(DEFAULT_RAW_ROOT).resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    compressed = path.read_bytes()
    expected_gzip = _text(artifact.get("gzip_sha256"))
    if expected_gzip and _sha256(compressed) != expected_gzip:
        return None
    try:
        raw = gzip.decompress(compressed)
    except (OSError, gzip.BadGzipFile):
        return None
    expected_raw = _text(artifact.get("sha256"))
    if expected_raw and _sha256(raw) != expected_raw:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _enrich_retained_osv(payload: dict[str, Any]) -> None:
    tool = _text(payload.get("scanner_name") or payload.get("tool")).casefold().replace("_", "-")
    if tool != "osv-scanner":
        return
    raw = _retained_raw_json(payload)
    if raw is None:
        payload["dependency_context_enrichment"] = {
            "status": "review_required",
            "reason": "retained exact-SHA OSV JSON could not be decoded",
        }
        return
    enriched: list[dict[str, Any]] = []
    _walk_osv(raw, {}, enriched)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in enriched:
        key = json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
    if selected:
        payload["findings"] = selected
        payload["findings_count"] = len(selected)
    payload["dependency_context_enrichment"] = {
        "status": "complete" if selected else "review_required",
        "raw_vulnerability_count": len(selected),
        "package_context_retained": bool(selected) and all(_text(item.get("package")) for item in selected),
        "installed_version_retained": bool(selected) and all(_text(item.get("installed_version")) for item in selected),
        "advisory_identity_retained": bool(selected) and all(
            _text(item.get("id") or (item.get("aliases") or [""])[0]) for item in selected
        ),
        "fixed_version_guidance_retained": bool(selected) and all(
            bool(item.get("fixed_versions") or item.get("fixed_version")) for item in selected
        ),
    }


def completed_scanner_tool_runner(
    specification: scanner_tool_runners.ScannerToolSpec,
    workspace: WorkerWorkspace,
    *,
    runner: Callable[..., WorkerCommandResult] = run_command,
    preparation: Any = None,
) -> dict[str, Any]:
    previous = getattr(completed_scanner_tool_runner, "_nico_previous")
    payload = previous(specification, workspace, runner=runner, preparation=preparation)
    if not isinstance(payload, dict):
        raise TypeError(f"scanner evidence completion requires an object payload: {specification.name}")
    output = deepcopy(payload)
    _enrich_retained_osv(output)
    output["scanner_evidence_completion"] = {
        "version": VERSION,
        "retained_raw_artifact_reopened_before_workspace_deletion": True,
        "osv_package_version_path_context_enriched": specification.name == "osv-scanner",
    }
    safe = redact_payload(output)
    safe["artifact_hash"] = _sha256(
        json.dumps(
            {key: value for key, value in safe.items() if key != "artifact_hash"},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    return safe


def _materialize_git_objects(
    repository: Path,
    environment: Mapping[str, str],
    notes: list[str],
) -> tuple[list[str], bool]:
    shallow = _git(repository, environment, "rev-parse", "--is-shallow-repository", timeout=30)
    if shallow.returncode != 0:
        return [*notes, "Git repository depth could not be verified for history-aware secret scanning."], False
    if _text(shallow.stdout).casefold() == "true":
        unshallow = _git(repository, environment, "fetch", "--unshallow", "--tags", "origin", timeout=900)
        if unshallow.returncode != 0:
            return [*notes, f"Full Git history could not be restored: {_text(unshallow.stderr)[:500]}"], False

    partial = any(_config(repository, environment, key) for key in _PARTIAL_CLONE_KEYS)
    if partial:
        for key in _PARTIAL_CLONE_KEYS:
            _git(repository, environment, "config", "--unset-all", key, timeout=30)
        refetch = _git(
            repository,
            environment,
            "fetch",
            "--refetch",
            "--tags",
            "--prune",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
            timeout=1200,
        )
        if refetch.returncode != 0:
            fallback = _git(
                repository,
                environment,
                "fetch",
                "--tags",
                "--prune",
                "origin",
                "+refs/heads/*:refs/remotes/origin/*",
                timeout=1200,
            )
            if fallback.returncode != 0:
                return [
                    *notes,
                    f"Partial-clone objects could not be materialized: {_text(fallback.stderr or refetch.stderr)[:500]}",
                ], False

    repack = _git(repository, environment, "repack", "-a", "-d", timeout=1200)
    if repack.returncode != 0:
        return [*notes, f"Full-object repository repack failed: {_text(repack.stderr)[:500]}"], False
    depth = _git(repository, environment, "rev-parse", "--is-shallow-repository", timeout=30)
    missing = _git(repository, environment, "rev-list", "--objects", "--all", "--missing=print", timeout=1200)
    fsck = _git(repository, environment, "fsck", "--full", "--no-dangling", timeout=1200)
    missing_objects = [line for line in (missing.stdout or "").splitlines() if line.startswith("?")]
    valid = (
        depth.returncode == 0
        and _text(depth.stdout).casefold() == "false"
        and missing.returncode == 0
        and not missing_objects
        and fsck.returncode == 0
        and not any(_config(repository, environment, key) for key in _PARTIAL_CLONE_KEYS)
    )
    if not valid:
        reason = _text(fsck.stderr or fsck.stdout or missing.stderr or "full object verification failed")[:500]
        return [*notes, f"Full Git object verification failed: {reason}"], False
    return [
        *notes,
        "Full Git history and object store were materialized and verified for Gitleaks and TruffleHog.",
    ], True


def completed_full_history_clone(
    repository: str,
    commit_sha: str,
    workspace: Path,
    environment: dict[str, str],
) -> tuple[Path | None, str, list[str]]:
    previous = getattr(completed_full_history_clone, "_nico_previous")
    repository_path, actual_sha, notes = previous(repository, commit_sha, workspace, environment)
    if repository_path is None or os.getenv("NICO_ENABLE_FULL_HISTORY_SECRET_SCAN", "false").casefold() != "true":
        return repository_path, actual_sha, notes
    try:
        repaired_notes, materialized = _materialize_git_objects(repository_path, environment, list(notes))
        observed = _git(repository_path, environment, "rev-parse", "HEAD", timeout=30)
        observed_sha = _text(observed.stdout).casefold() if observed.returncode == 0 else ""
        if observed_sha != _text(commit_sha).casefold():
            repaired_notes.append("Object materialization did not preserve the exact assessed commit identity.")
        elif not materialized:
            repaired_notes.append("Gitleaks and TruffleHog must remain unverified until the full object store is available.")
        return repository_path, actual_sha, repaired_notes
    except Exception as exc:
        return repository_path, actual_sha, [
            *notes,
            f"Full-history object materialization failed safely: {type(exc).__name__}: {_text(exc)}",
        ]


def install_v2_scanner_evidence_completion() -> dict[str, Any]:
    current_tool = scanner_tool_runners.run_scanner_tool
    if not getattr(current_tool, _TOOL_MARKER, False):
        setattr(completed_scanner_tool_runner, "_nico_previous", current_tool)
        setattr(completed_scanner_tool_runner, _TOOL_MARKER, True)
        scanner_tool_runners.run_scanner_tool = completed_scanner_tool_runner

    current_clone = snapshot_scanner_worker.clone_repository_at_snapshot
    if not getattr(current_clone, _CLONE_MARKER, False):
        setattr(completed_full_history_clone, "_nico_previous", current_clone)
        setattr(completed_full_history_clone, _CLONE_MARKER, True)
        snapshot_scanner_worker.clone_repository_at_snapshot = completed_full_history_clone

    tool_bound = scanner_tool_runners.run_scanner_tool is completed_scanner_tool_runner
    clone_bound = snapshot_scanner_worker.clone_repository_at_snapshot is completed_full_history_clone
    return {
        "status": "installed" if tool_bound and clone_bound else "blocked",
        "version": VERSION,
        "bound": tool_bound and clone_bound,
        "retained_osv_json_reopened": tool_bound,
        "osv_package_version_path_context_retained": tool_bound,
        "partial_clone_configuration_detected": clone_bound,
        "partial_clone_objects_refetched": clone_bound,
        "full_object_store_repacked_and_verified": clone_bound,
        "trufflehog_internal_clone_supported": clone_bound,
        "exact_commit_identity_preserved": clone_bound,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "completed_scanner_tool_runner",
    "completed_full_history_clone",
    "install_v2_scanner_evidence_completion",
]
