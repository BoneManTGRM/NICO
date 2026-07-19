from __future__ import annotations

import io
import re
import shutil
import urllib.request
import zipfile
from functools import wraps
from pathlib import Path
from typing import Any, Callable

PATCH_VERSION = "nico.snapshot_checkout_reliability.v1"
_PATCH_MARKER = "_nico_snapshot_checkout_reliability_v1"
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_MAX_ARCHIVE_BYTES = 250_000_000


def _archive_checkout(repository: str, commit_sha: str, workspace: Path) -> tuple[Path | None, str, list[str]]:
    """Fetch an immutable GitHub source archive when git transport is unavailable.

    The archive is bound to the exact commit SHA. It intentionally contains no
    git history, so history-only scanners remain unavailable while dependency and
    static-analysis scanners can still run against the correct source snapshot.
    """
    repository = str(repository or "").strip()
    commit_sha = str(commit_sha or "").strip().lower()
    if not _REPOSITORY_RE.fullmatch(repository) or not _COMMIT_RE.fullmatch(commit_sha):
        return None, "", ["Exact snapshot archive fallback requires owner/name and a full commit SHA."]

    url = f"https://codeload.github.com/{repository}/zip/{commit_sha}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "NICO-snapshot-worker"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read(_MAX_ARCHIVE_BYTES + 1)
    except Exception as exc:
        return None, "", [f"exact snapshot archive fallback failed safely: {type(exc).__name__}"]

    if len(payload) > _MAX_ARCHIVE_BYTES:
        return None, "", ["Exact snapshot archive exceeded the bounded download limit."]

    repo_path = workspace / "repo"
    shutil.rmtree(repo_path, ignore_errors=True)
    repo_path.mkdir(parents=True, exist_ok=True)
    extracted_files = 0
    extracted_bytes = 0
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for member in archive.infolist():
                path = Path(member.filename)
                parts = path.parts[1:] if len(path.parts) > 1 else ()
                if not parts or member.is_dir():
                    continue
                if any(part in {"", ".", ".."} for part in parts):
                    raise ValueError("unsafe archive path")
                target = repo_path.joinpath(*parts)
                resolved = target.resolve()
                if repo_path.resolve() not in resolved.parents:
                    raise ValueError("archive path escaped workspace")
                extracted_bytes += int(member.file_size or 0)
                if extracted_bytes > _MAX_ARCHIVE_BYTES:
                    raise ValueError("archive extraction exceeded bounded limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted_files += 1
    except Exception as exc:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, "", [f"exact snapshot archive extraction failed safely: {type(exc).__name__}"]

    if extracted_files == 0:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, "", ["Exact snapshot archive contained no repository files."]
    return repo_path, commit_sha, [
        "Git transport was unavailable; NICO used the immutable exact-commit source archive. Git-history scanners are unavailable for this run."
    ]


def install_snapshot_checkout_reliability() -> dict[str, Any]:
    from nico import snapshot_scanner_worker

    current: Callable[..., tuple[Path | None, str, list[str]]] = snapshot_scanner_worker.clone_repository_at_snapshot
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def reliable_checkout(repository: str, commit_sha: str, workspace: Path, env: dict[str, str]):
        notes: list[str] = []
        last_actual_sha = ""
        for attempt in range(1, 3):
            shutil.rmtree(workspace / "repo", ignore_errors=True)
            repo_path, actual_sha, attempt_notes = current(repository, commit_sha, workspace, env)
            if actual_sha:
                last_actual_sha = str(actual_sha).strip().lower()
            notes.extend(f"git attempt {attempt}: {note}" for note in attempt_notes)
            if repo_path is not None and last_actual_sha == str(commit_sha or "").lower():
                return repo_path, last_actual_sha, notes
        archive_path, archive_sha, archive_notes = _archive_checkout(repository, commit_sha, workspace)
        notes.extend(archive_notes)
        if archive_path is not None:
            return archive_path, archive_sha, notes
        return None, last_actual_sha, notes

    setattr(reliable_checkout, _PATCH_MARKER, True)
    setattr(reliable_checkout, "_nico_previous", current)
    snapshot_scanner_worker.clone_repository_at_snapshot = reliable_checkout
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "git_attempts": 2,
        "exact_commit_archive_fallback": True,
        "archive_path_validation": True,
        "history_scanners_fail_closed_without_git": True,
        "mismatch_evidence_preserved": True,
    }


__all__ = ["PATCH_VERSION", "_archive_checkout", "install_snapshot_checkout_reliability"]
