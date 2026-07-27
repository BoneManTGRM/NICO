from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

VERSION = "nico.evidence_pipeline_repair.v1"
_PATCH_MARKER = "_nico_evidence_pipeline_repair_v1"
_EXACT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_GENERATED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage_html",
}
_ESLINT_CONFIG_NAMES = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
)
_REQUIRED_REPEATABILITY_TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)


def _exact_sha(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if _EXACT_SHA_RE.fullmatch(text) else ""


def _immutable_sha(result: dict[str, Any]) -> str:
    preferred = (
        "immutable_commit_sha",
        "immutable_commit",
        "target_commit_sha",
        "resolved_commit_sha",
        "repository_commit_sha",
        "commit_sha",
        "commit",
        "sha",
    )
    queue: list[tuple[dict[str, Any], int]] = [(result, 0)]
    seen: set[int] = set()
    while queue:
        payload, depth = queue.pop(0)
        if id(payload) in seen:
            continue
        seen.add(id(payload))
        for key in preferred:
            value = _exact_sha(payload.get(key))
            if value:
                return value
        if depth >= 3:
            continue
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(part in lowered for part in ("application", "deployment", "worker_image")):
                continue
            if isinstance(value, dict):
                queue.append((value, depth + 1))
    return ""


def _skip_generated(path: Path, repo_dir: Path) -> bool:
    try:
        relative = path.resolve().relative_to(repo_dir.resolve())
    except ValueError:
        return True
    return any(part in _GENERATED_PARTS for part in relative.parts)


def _package_dirs(repo_dir: Path) -> list[Path]:
    roots: set[Path] = set()
    for package_json in repo_dir.rglob("package.json"):
        if _skip_generated(package_json, repo_dir):
            continue
        try:
            relative = package_json.relative_to(repo_dir)
        except ValueError:
            continue
        if len(relative.parts) > 7:
            continue
        roots.add(package_json.parent)
    return sorted(
        roots,
        key=lambda path: (
            0 if path == repo_dir / "apps" / "web" else 1,
            len(path.relative_to(repo_dir).parts),
            str(path),
        ),
    )


def _nearest_lock_root(project_dir: Path, repo_dir: Path) -> Path | None:
    current = project_dir
    repo_dir = repo_dir.resolve()
    while True:
        if (current / "package-lock.json").is_file() and (current / "package.json").is_file():
            return current
        if current.resolve() == repo_dir or current.parent == current:
            return None
        current = current.parent


def _eslint_config_exists(project_dir: Path) -> bool:
    return any((project_dir / name).is_file() for name in _ESLINT_CONFIG_NAMES)


def _select_node_project(repo_dir: Path, tool_name: str) -> tuple[Path, Path] | None:
    for project_dir in _package_dirs(repo_dir):
        if tool_name == "typescript" and not (project_dir / "tsconfig.json").is_file():
            continue
        if tool_name == "eslint" and not _eslint_config_exists(project_dir):
            continue
        lock_root = _nearest_lock_root(project_dir, repo_dir)
        if lock_root is not None:
            return project_dir, lock_root
    return None


def _not_applicable(spec: Any, reason: str) -> dict[str, Any]:
    return {
        "tool": spec.name,
        "status": "not_applicable",
        "category": spec.category,
        "returncode": 0,
        "returncode_valid": True,
        "timed_out": False,
        "output_truncated": False,
        "output_capture_complete": True,
        "findings": [],
        "findings_count": 0,
        "stderr": "",
        "reason": reason,
        "scans_git_history": bool(spec.scans_git_history),
        "full_history_verified": False,
        "verified_for_this_report": True,
        "execution_observed_for_this_report": True,
        "current_run": True,
        "evidence_limitation": False,
    }


def _prepare_node_project(
    runners: Any,
    workspace: Any,
    lock_root: Path,
    *,
    runner: Callable[..., Any],
) -> Any:
    npm = shutil.which("npm")
    if not npm:
        return runners.ProjectCommandPreparation(
            "unavailable",
            lock_root,
            False,
            "npm is not installed in the worker image.",
        )
    output_path = workspace.root / "scanner-output" / f"npm-ci-{hashlib.sha256(str(lock_root).encode()).hexdigest()[:12]}.stdout"
    result = runner(
        (
            npm,
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--prefer-offline",
        ),
        cwd=lock_root,
        limits=runners.WorkerLimits(timeout_seconds=600, max_output_chars=500_000),
        extra_env=runners._node_env(workspace, lock_root),
        stdout_path=output_path,
    )
    ready = result.returncode == 0 and not result.timed_out and (lock_root / "node_modules").is_dir()
    reason = "" if ready else runners.redact_text(result.stderr or result.stdout or "npm ci did not establish node_modules")[:4000]
    return runners.ProjectCommandPreparation(
        "completed" if ready else "failed",
        lock_root,
        ready,
        reason,
        returncode=result.returncode,
        timed_out=result.timed_out,
        output_truncated=result.output_truncated,
    )


def _remove_gitleaks_head_scope(command: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            skip_next = False
            continue
        if part == "--log-opts":
            skip_next = True
            continue
        output.append(str(part))
    return tuple(output)


def _effective_command(spec: Any, command: tuple[str, ...]) -> tuple[str, ...]:
    if spec.name == "gitleaks":
        return _remove_gitleaks_head_scope(command)
    if spec.name == "bandit" and "-x" not in command and "--exclude" not in command:
        return command + ("-x", ",".join(sorted(_GENERATED_PARTS)))
    return command


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_output_record(result: Any) -> dict[str, Any] | None:
    path_text = str(getattr(result, "stdout_path", "") or "")
    if not path_text:
        return None
    path = Path(path_text)
    try:
        size = path.stat().st_size
        digest = _file_sha256(path)
    except OSError:
        return None

    configured_root = str(os.getenv("NICO_SCANNER_ARTIFACT_DIR") or "").strip()
    archive_root = (
        Path(configured_root).expanduser()
        if configured_root
        else Path(tempfile.gettempdir()) / "nico-scanner-artifacts"
    )
    archive_path = archive_root / f"{digest}-{path.name}.gz"
    retained = False
    archive_sha256 = ""
    archive_bytes = 0
    retention_error = ""
    try:
        archive_root.mkdir(parents=True, exist_ok=True)
        if not archive_path.exists():
            with path.open("rb") as source, gzip.open(archive_path, "wb", compresslevel=6) as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
        archive_sha256 = _file_sha256(archive_path)
        archive_bytes = archive_path.stat().st_size
        retained = True
    except OSError as exc:
        retention_error = type(exc).__name__

    return {
        "filename": path.name,
        "sha256": digest,
        "bytes": size,
        "capture_complete": True,
        "retained_as_structured_findings": True,
        "raw_archive_retained": retained,
        "raw_archive_filename": archive_path.name if retained else None,
        "raw_archive_path": str(archive_path) if retained else None,
        "raw_archive_sha256": archive_sha256 or None,
        "raw_archive_bytes": archive_bytes,
        "retention_scope": "configured_artifact_directory" if configured_root else "process_filesystem",
        "durability_verified": bool(configured_root and retained),
        "retention_error": retention_error,
    }


__all__ = [
    "VERSION", "_REQUIRED_REPEATABILITY_TOOLS", "_exact_sha", "_immutable_sha",
    "_select_node_project", "_not_applicable", "_prepare_node_project",
    "_effective_command", "_raw_output_record", "_skip_generated",
]
