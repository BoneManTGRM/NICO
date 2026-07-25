from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_REF_RE = re.compile(r"^[A-Za-z0-9._/@+-]{1,160}$")
BLOCKED_REF_PARTS = ("..", "//", "\\", " ", "\t", "\n", "\r", "~", "^", ":", "?", "*", "[")


class WorkerExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerLimits:
    timeout_seconds: int = 60
    max_output_chars: int = 16_000


@dataclass(frozen=True)
class WorkerCommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    output_truncated: bool = False
    stdout_path: str | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True)
class WorkerWorkspace:
    root: Path

    @property
    def repo_dir(self) -> Path:
        return self.root / "repo"


def validate_repository(repository: str) -> str:
    value = (repository or "").strip()
    value = value.replace("https://github.com/", "").replace("http://github.com/", "")
    value = value.replace("git@github.com:", "")
    value = value.strip("/")

    if value.endswith(".git"):
        value = value[:-4]

    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError("repository must be owner/name")

    owner, repo = parts
    value = f"{owner}/{repo}"
    if not SAFE_REPO_RE.fullmatch(value):
        raise ValueError("repository must be owner/name")
    return value


def validate_ref(ref: str) -> str:
    value = (ref or "").strip()
    if not value or not SAFE_REF_RE.fullmatch(value):
        raise ValueError("ref contains unsupported characters")
    if value.startswith(("/", "-")) or value.endswith(("/", ".", ".lock")):
        raise ValueError("ref has unsafe boundary characters")
    if any(part in value for part in BLOCKED_REF_PARTS):
        raise ValueError("ref contains unsafe sequence")
    return value


def make_workspace(prefix: str = "nico-worker-") -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix)


def workspace_from_temp(temp_dir: tempfile.TemporaryDirectory[str]) -> WorkerWorkspace:
    root = Path(temp_dir.name).resolve()
    return WorkerWorkspace(root=root)


def _clean_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    allowed = {
        "HOME": os.getenv("HOME", ""),
        "PATH": os.getenv("PATH", ""),
        "LANG": os.getenv("LANG", "C.UTF-8"),
        "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
    }
    if extra_env:
        for key, value in extra_env.items():
            normalized = str(key).upper()
            if normalized in {"TOKEN", "SECRET", "PASSWORD", "API_KEY"}:
                continue
            allowed[str(key)] = str(value)
    return allowed


def _truncate(value: str, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    marker = "\n...[truncated by NICO worker]"
    keep = max(0, max_chars - len(marker))
    return value[:keep] + marker, True


def _decode_timeout_value(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _read_file_preview(path: Path, max_chars: int) -> tuple[str, bool, int]:
    try:
        byte_count = path.stat().st_size
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            value = handle.read(max_chars + 1)
    except OSError:
        return "", False, 0
    if len(value) <= max_chars:
        return value, False, byte_count
    preview, _ = _truncate(value, max_chars)
    return preview, True, byte_count


def run_command(
    args: Sequence[str],
    *,
    cwd: Path,
    limits: WorkerLimits | None = None,
    extra_env: dict[str, str] | None = None,
    stdout_path: Path | None = None,
) -> WorkerCommandResult:
    if not args:
        raise ValueError("args must not be empty")
    if any(not isinstance(part, str) or not part for part in args):
        raise ValueError("args must be non-empty strings")
    limits = limits or WorkerLimits()
    cwd = cwd.resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise ValueError("cwd must exist and be a directory")

    output_handle = None
    resolved_stdout_path: Path | None = None
    if stdout_path is not None:
        resolved_stdout_path = stdout_path.resolve()
        resolved_stdout_path.parent.mkdir(parents=True, exist_ok=True)
        output_handle = resolved_stdout_path.open("w", encoding="utf-8", errors="replace")

    try:
        try:
            completed = subprocess.run(
                list(args),
                cwd=str(cwd),
                env=_clean_env(extra_env),
                stdout=output_handle if output_handle is not None else subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=limits.timeout_seconds,
                check=False,
                shell=False,
                start_new_session=True,
            )
            if output_handle is not None:
                output_handle.flush()
                stdout, out_truncated, stdout_bytes = _read_file_preview(resolved_stdout_path, limits.max_output_chars)  # type: ignore[arg-type]
            else:
                stdout, out_truncated = _truncate(completed.stdout or "", limits.max_output_chars)
                stdout_bytes = len((completed.stdout or "").encode("utf-8", errors="replace"))
            stderr, err_truncated = _truncate(completed.stderr or "", limits.max_output_chars)
            return WorkerCommandResult(
                args=tuple(args),
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                output_truncated=out_truncated or err_truncated,
                stdout_path=str(resolved_stdout_path) if resolved_stdout_path is not None else None,
                stdout_bytes=stdout_bytes,
                stderr_bytes=len((completed.stderr or "").encode("utf-8", errors="replace")),
            )
        except subprocess.TimeoutExpired as exc:
            if output_handle is not None:
                output_handle.flush()
                stdout, out_truncated, stdout_bytes = _read_file_preview(resolved_stdout_path, limits.max_output_chars)  # type: ignore[arg-type]
            else:
                raw_stdout = _decode_timeout_value(exc.stdout)
                stdout, out_truncated = _truncate(raw_stdout, limits.max_output_chars)
                stdout_bytes = len(raw_stdout.encode("utf-8", errors="replace"))
            raw_stderr = _decode_timeout_value(exc.stderr)
            stderr, err_truncated = _truncate(raw_stderr, limits.max_output_chars)
            return WorkerCommandResult(
                args=tuple(args),
                returncode=124,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
                output_truncated=out_truncated or err_truncated,
                stdout_path=str(resolved_stdout_path) if resolved_stdout_path is not None else None,
                stdout_bytes=stdout_bytes,
                stderr_bytes=len(raw_stderr.encode("utf-8", errors="replace")),
            )
    finally:
        if output_handle is not None:
            output_handle.close()


def checkout_repository(repository: str, ref: str, workspace: WorkerWorkspace, limits: WorkerLimits | None = None) -> WorkerCommandResult:
    repository = validate_repository(repository)
    ref = validate_ref(ref)
    if workspace.repo_dir.exists():
        raise WorkerExecutionError("workspace repo directory already exists")
    clone_url = f"https://github.com/{repository}.git"
    return run_command(
        ("git", "clone", "--depth", "1", "--no-tags", "--branch", ref, clone_url, str(workspace.repo_dir)),
        cwd=workspace.root,
        limits=limits or WorkerLimits(timeout_seconds=120, max_output_chars=12_000),
    )


def cleanup_workspace(workspace: WorkerWorkspace) -> None:
    if workspace.root.exists():
        shutil.rmtree(workspace.root, ignore_errors=True)
