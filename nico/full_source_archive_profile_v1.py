from __future__ import annotations

import io
import os
import zipfile
from functools import wraps
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import quote

import requests

VERSION = "nico.full_source_archive_profile.v1"
_PATCH_MARKER = "_nico_full_source_archive_profile_v1"
MAX_ARCHIVE_BYTES = int(os.getenv("NICO_MAX_SOURCE_ARCHIVE_BYTES", str(120 * 1024 * 1024)))
MAX_SOURCE_FILES = int(os.getenv("NICO_MAX_ARCHIVE_SOURCE_FILES", "2500"))
MAX_SOURCE_FILE_BYTES = int(os.getenv("NICO_MAX_ARCHIVE_SOURCE_FILE_BYTES", str(600_000)))
MAX_TOTAL_SOURCE_BYTES = int(os.getenv("NICO_MAX_ARCHIVE_SOURCE_TOTAL_BYTES", str(90 * 1024 * 1024)))
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", ".next", "dist", "build", "vendor", "coverage", "coverage_html", "__pycache__"}


def _eligible(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts or any(part.casefold() in SKIP_PARTS for part in parts):
        return False
    lowered = path.casefold()
    if PurePosixPath(path).suffix.casefold() not in SOURCE_SUFFIXES:
        return False
    if lowered.endswith((".min.js", ".min.jsx")):
        return False
    return True


def _download_archive(client: Any, repository: str, ref: str) -> bytes:
    url = client.repo_url(repository, f"/zipball/{quote(ref, safe='')}")
    response = requests.get(url, headers=client.headers, timeout=(15, 90), stream=True, allow_redirects=True)
    response.raise_for_status()
    buffer = io.BytesIO()
    for chunk in response.iter_content(chunk_size=1024 * 1024):
        if not chunk:
            continue
        buffer.write(chunk)
        if buffer.tell() > MAX_ARCHIVE_BYTES:
            raise ValueError(f"source archive exceeded {MAX_ARCHIVE_BYTES} bytes")
    return buffer.getvalue()


def _archive_sources(data: bytes) -> tuple[dict[str, str], dict[str, Any]]:
    files: dict[str, str] = {}
    total_bytes = 0
    skipped_large = 0
    skipped_limit = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        for member in members:
            parts = PurePosixPath(member.filename).parts
            relative = PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else ""
            if not relative or not _eligible(relative):
                continue
            if member.file_size > MAX_SOURCE_FILE_BYTES:
                skipped_large += 1
                continue
            if len(files) >= MAX_SOURCE_FILES or total_bytes + member.file_size > MAX_TOTAL_SOURCE_BYTES:
                skipped_limit += 1
                continue
            raw = archive.read(member)
            files[relative] = raw.decode("utf-8", errors="replace")
            total_bytes += len(raw)
    return files, {
        "source_files_loaded": len(files),
        "source_bytes_loaded": total_bytes,
        "source_files_skipped_large": skipped_large,
        "source_files_skipped_limit": skipped_limit,
        "source_file_limit": MAX_SOURCE_FILES,
        "source_total_byte_limit": MAX_TOTAL_SOURCE_BYTES,
        "exact_sha_archive": True,
    }


def install_full_source_archive_profile_v1() -> dict[str, Any]:
    from nico import snapshot_repository_evidence as snapshot

    current: Callable[..., dict[str, Any]] = snapshot._profile
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def profile(client: Any, repository: str, captured: dict[str, Any]) -> dict[str, Any]:
        result = current(client, repository, captured)
        commit_sha = str(captured.get("commit_sha") or "").strip()
        if not commit_sha:
            result.setdefault("unavailable", []).append("Exact-SHA source archive was unavailable because the snapshot commit was missing.")
            return result
        try:
            archive = _download_archive(client, repository, commit_sha)
            source_files, metadata = _archive_sources(archive)
        except Exception as exc:
            result.setdefault("unavailable", []).append(
                f"Exact-SHA source archive profiling was unavailable: {type(exc).__name__}. Existing bounded file evidence remains visible."
            )
            result["archive_source_profile"] = {
                "status": "unavailable",
                "version": VERSION,
                "snapshot_commit_sha": commit_sha,
                "reason": type(exc).__name__,
            }
            return result

        existing = result.get("files") if isinstance(result.get("files"), dict) else {}
        existing.update(source_files)
        result["files"] = existing
        result["archive_source_profile"] = {
            "status": "attached",
            "version": VERSION,
            "snapshot_commit_sha": commit_sha,
            "archive_bytes": len(archive),
            **metadata,
        }
        return result

    setattr(profile, _PATCH_MARKER, True)
    snapshot._profile = profile
    return {
        "status": "installed",
        "version": VERSION,
        "exact_sha_archive": True,
        "full_first_party_source_profile": True,
        "generated_and_dependency_paths_excluded": True,
        "bounded_archive_and_source_bytes": True,
    }


__all__ = ["VERSION", "install_full_source_archive_profile_v1"]
