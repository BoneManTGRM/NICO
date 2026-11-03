from __future__ import annotations

import os
import io
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_REF_RE = re.compile(r"^[A-Za-z0-9._/@+-]{1,160}$")
BLOCKED_REF_PARTS = ("..", "//", "\\", " ", "\t", "\n", "\r", "~", "^", ":", "?", "*", "[")


class WorkerExecutionError(RuntimeError):
    pass


class WorkerCleanupError(BaseException):
    """Abort orchestration, not an ordinary tool failure that permits the next tool.

    Snapshot/hosted adapters catch Exception per tool. This control-plane failure
    deliberately crosses those handlers; even callers catching BaseException cannot
    launch another command through this runner once the process-local latch is set.
    """


_CLEANUP_UNCERTAIN = threading.Event()
_TERM_GRACE_SECONDS = 1.0
_KILL_WAIT_SECONDS = 1.0
_DRAIN_SECONDS = 1.0


def _live_group(group: int) -> bool:
    """Linux: zombies cannot consume CPU or hold output descriptors open."""
    if not Path('/proc/self/stat').is_file():
        # Other POSIX systems can prove absence, but cannot classify zombies here.
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return False
        return True
    deadline = time.monotonic() + 0.5
    with os.scandir('/proc') as entries:
        for entry in entries:
            if time.monotonic() > deadline:
                raise WorkerCleanupError('process inventory deadline exceeded')
            if not entry.name.isdigit():
                continue
            try:
                fields = Path(entry.path, 'stat').read_text().rsplit(')', 1)[1].split()
            except FileNotFoundError:
                continue
            if int(fields[2]) == group and fields[0] not in {'Z', 'X'}:
                if int(fields[3]) != group:
                    raise WorkerCleanupError('owned process group session mismatch')
                return True
    return False


def _cleanup_group(process: subprocess.Popen, group: int) -> None:
    # group is only the PID returned by our start_new_session=True Popen.
    if group <= 1 or group != process.pid or group == os.getpgrp():
        raise WorkerCleanupError('unsafe worker process group')
    for sig, allowance in ((signal.SIGTERM, _TERM_GRACE_SECONDS),
                           (signal.SIGKILL, _KILL_WAIT_SECONDS)):
        if _live_group(group):
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + allowance
        while _live_group(group):
            if time.monotonic() >= deadline:
                break
            process.poll()
            time.sleep(0.02)
        else:
            try:
                process.wait(timeout=_KILL_WAIT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise WorkerCleanupError('direct child reap unconfirmed') from exc
            return
    raise WorkerCleanupError('worker process group termination unconfirmed')


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
    scanner_execution_receipt: dict | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(frozen=True)
class WorkerWorkspace:
    root: Path
    # Captured once by the snapshot worker before any tool prepares dependencies.
    node_input_inventory: dict | None = None
    package_input_inventory: dict | None = None

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
    if _CLEANUP_UNCERTAIN.is_set():
        raise WorkerCleanupError("prior worker cleanup unconfirmed; command launch blocked")
    if os.name != "posix":
        raise WorkerExecutionError("owned process-group execution requires POSIX")

    output_handle = None
    resolved_stdout_path: Path | None = None
    if stdout_path is not None:
        resolved_stdout_path = stdout_path.resolve()
        resolved_stdout_path.parent.mkdir(parents=True, exist_ok=True)
        output_handle = resolved_stdout_path.open("w", encoding="utf-8", errors="replace")

    process = None
    cleanup_attempted = False
    try:
        if _CLEANUP_UNCERTAIN.is_set():
            raise WorkerCleanupError("prior worker cleanup unconfirmed; command launch blocked")
        process = subprocess.Popen(
            list(args), cwd=str(cwd), env=_clean_env(extra_env),
            stdout=output_handle if output_handle is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False, start_new_session=True,
        )
        timed_out = False
        try:
            process.communicate(timeout=limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        # Preserve the direct command's status before cleaning surviving descendants.
        normal_returncode = process.returncode
        try:
            cleanup_attempted = True
            _cleanup_group(process, process.pid)
            # communicate retains prior buffers; never concatenate TimeoutExpired output.
            raw_stdout, raw_stderr = process.communicate(timeout=_DRAIN_SECONDS)
        except BaseException as exc:
            _CLEANUP_UNCERTAIN.set()
            raise WorkerCleanupError("worker cleanup or output drain unconfirmed") from exc
        # Decode only after cleanup. Normal text capture retains Python's strict
        # default encoding/newline behavior; TimeoutExpired historically exposed
        # bytes decoded by our UTF-8 replacement helper instead.
        def decode(value):
            if timed_out:
                return _decode_timeout_value(value)
            with io.TextIOWrapper(io.BytesIO(value or b''), encoding=None) as stream:
                return stream.read()
        raw_stdout, raw_stderr = decode(raw_stdout), decode(raw_stderr)
        if output_handle is not None:
            output_handle.flush()
            stdout, out_truncated, stdout_bytes = _read_file_preview(resolved_stdout_path, limits.max_output_chars)
        else:
            stdout, out_truncated = _truncate(raw_stdout, limits.max_output_chars)
            stdout_bytes = len(raw_stdout.encode("utf-8", errors="replace"))
        stderr, err_truncated = _truncate(raw_stderr, limits.max_output_chars)
        return WorkerCommandResult(
            args=tuple(args), returncode=124 if timed_out else normal_returncode,
            stdout=stdout, stderr=stderr, timed_out=timed_out,
            output_truncated=out_truncated or err_truncated,
            stdout_path=str(resolved_stdout_path) if resolved_stdout_path is not None else None,
            stdout_bytes=stdout_bytes,
            stderr_bytes=len(raw_stderr.encode("utf-8", errors="replace")),
        )
    except BaseException:
        if process is not None and not cleanup_attempted:
            try:
                _cleanup_group(process, process.pid)
                process.communicate(timeout=_DRAIN_SECONDS)
            except BaseException as cleanup_error:
                _CLEANUP_UNCERTAIN.set()
                raise WorkerCleanupError("exception cleanup unconfirmed; further launches blocked") from cleanup_error
        raise
    finally:
        if process is not None:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
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
