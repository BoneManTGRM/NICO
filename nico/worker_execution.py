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
    value = value.removesuffix(".git").strip("/")
    parts = value.split("/")
    if len(parts) >= 2:
        value = "/".join(parts[:2])
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
            if key.upper() in {"TOKEN", "SECRET", "PASSWORD", "API_KEY"}:
                continue
            allowed[str(key)] = str(value)
    return allowed


def _truncate(value: str, max_chars: int) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    marker = "\n...[truncated by NICO worker]"
    keep = max(0, max_chars - len(marker))
    return value[:keep] + marker, True


def run_command(
    args: Sequence[str],
    *,
    cwd: Path,
    limits: WorkerLimits | None = None,
    extra_env: dict[str, str] | None = None,
) -> WorkerCommandResult:
    if not args:
        raise ValueError("args must not be empty")
    if any(not isinstance(part, str) or not part for part in args):
        raise ValueError("args must be non-empty strings")
    limits = limits or WorkerLimits()
    cwd = cwd.resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise ValueError("cwd must exist and be a directory")

    try:
        completed = subprocess.run(
            list(args),
            cwd=str(cwd),
            env=_clean_env(extra_env),
            capture_output=True,
            text=True,
            timeout=limits.timeout_seconds,
            check=False,
            shell=False,
        )
        stdout, out_truncated = _truncate(completed.stdout or "", limits.max_output_chars)
        stderr, err_truncated = _truncate(completed.stderr or "", limits.max_output_chars)
        return WorkerCommandResult(
            args=tuple(args),
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            output_truncated=out_truncated or err_truncated,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, out_truncated = _truncate(exc.stdout or "", limits.max_output_chars)
        stderr, err_truncated = _truncate(exc.stderr or "", limits.max_output_chars)
        return WorkerCommandResult(
            args=tuple(args),
            returncode=124,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            output_truncated=out_truncated or err_truncated,
        )


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
