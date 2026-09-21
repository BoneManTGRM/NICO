from __future__ import annotations

import io
import os
import re
import stat
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
from nico.full_assessment_complexity_evidence import SOURCE_SUFFIXES as _SOURCE_SUFFIXES
SOURCE_SUFFIXES = set(_SOURCE_SUFFIXES)
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", ".next", "dist", "build", "vendor", "coverage", "coverage_html", "__pycache__"}


def lfs_pointer_entry(path: str, text: str) -> dict[str, Any] | None:
    """Retain pointer identity, never credit it as acquired external content."""
    if not text.startswith("version https://git-lfs.github.com/spec/v1\n") and not text.startswith("version https://git-lfs.github.com/spec/v1\r\n"):
        return None
    lines = text.splitlines()
    oids = [line[4:] for line in lines if re.fullmatch(r"oid sha256:[0-9a-f]{64}", line)]
    sizes = [int(line[5:]) for line in lines if re.fullmatch(r"size [0-9]{1,20}", line)]
    return {"path": path, "oid": oids[0] if len(oids) == 1 else None,
            "size_bytes": sizes[0] if len(sizes) == 1 else None}


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
    inventory: set[str] = set()
    size_excluded: list[str] = []
    limit_excluded: list[str] = []
    symlinks: list[str] = []
    lfs_entries: list[dict[str, Any]] = []
    inspected_files = inspected_bytes = 0
    source_file_bytes: dict[str, int] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = sorted((item for item in archive.infolist() if not item.is_dir()), key=lambda item: item.filename)
        for member in members:
            parts = PurePosixPath(member.filename).parts
            relative = PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else ""
            if not relative or not _eligible(relative):
                continue
            if ".." in parts or member.filename.startswith("/") or relative in inventory:
                raise ValueError("unsafe or duplicate source archive path")
            inventory.add(relative)
            if stat.S_ISLNK(member.external_attr >> 16):
                symlinks.append(relative)
                continue
            if member.file_size > MAX_SOURCE_FILE_BYTES:
                skipped_large += 1
                size_excluded.append(relative)
                continue
            if inspected_files >= MAX_SOURCE_FILES or inspected_bytes + member.file_size > MAX_TOTAL_SOURCE_BYTES:
                skipped_limit += 1
                limit_excluded.append(relative)
                continue
            raw = archive.read(member)
            inspected_files += 1
            inspected_bytes += len(raw)
            text = raw.decode("utf-8", errors="replace")
            pointer = lfs_pointer_entry(relative, text)
            if pointer is not None:
                lfs_entries.append(pointer)
                continue
            files[relative] = text
            source_file_bytes[relative] = len(raw)
            total_bytes += len(raw)
    return files, {
        "source_files_loaded": len(files),
        "source_bytes_loaded": total_bytes,
        "source_file_bytes": source_file_bytes,
        "source_files_inspected": inspected_files,
        "source_bytes_inspected": inspected_bytes,
        "source_files_skipped_large": skipped_large,
        "source_files_skipped_limit": skipped_limit,
        "source_file_limit": MAX_SOURCE_FILES,
        "source_per_file_byte_limit": MAX_SOURCE_FILE_BYTES,
        "source_total_byte_limit": MAX_TOTAL_SOURCE_BYTES,
        "source_inventory_paths": sorted(inventory),
        "source_size_excluded_paths": size_excluded,
        "source_limit_excluded_paths": limit_excluded,
        "symlink_paths_not_followed": symlinks,
        "lfs_pointer_entries": lfs_entries,
        "unavailable_paths": sorted(set(symlinks) | {row["path"] for row in lfs_entries}),
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
        unavailable_content = set(result.get("symlink_paths_not_followed") or []) | {
            row["path"] for row in result.get("submodule_entries") or []} | {
            row["path"] for row in result.get("lfs_pointer_entries") or []} | set(metadata["unavailable_paths"])
        for path in unavailable_content:
            existing.pop(path, None)
            source_files.pop(path, None)
        existing.update(source_files)
        metadata["source_files_loaded"] = len(source_files)
        metadata["source_bytes_loaded"] = sum(metadata["source_file_bytes"][path] for path in source_files)
        metadata["source_file_bytes"] = {path: metadata["source_file_bytes"][path] for path in source_files}
        result["files"] = existing
        # Archive sampling can extend a truncated API inventory. Retain the
        # observed paths before coverage validates membership, without claiming
        # that an incomplete API inventory became a complete repository tree.
        result["tree_paths"] = sorted(set(result.get("tree_paths") or []) | set(metadata["source_inventory_paths"]))
        result["unavailable_paths"] = sorted((set(result.get("unavailable_paths") or []) | unavailable_content) - set(source_files))
        result["symlink_paths_not_followed"] = sorted(set(result.get("symlink_paths_not_followed") or []) | set(metadata["symlink_paths_not_followed"]))
        pointers = {row["path"]: row for row in result.get("lfs_pointer_entries") or []}
        pointers.update({row["path"]: row for row in metadata["lfs_pointer_entries"]})
        result["lfs_pointer_entries"] = [pointers[path] for path in sorted(pointers)]
        result["size_excluded_paths"] = sorted((set(result.get("size_excluded_paths") or []) | set(metadata["source_size_excluded_paths"])) - set(existing))
        from nico.hosted_assessment import MAX_FILE_BYTES, MAX_TEXT_FILES
        result["profile_limits"] = {
            "file_limit": MAX_TEXT_FILES + MAX_SOURCE_FILES,
            "per_file_byte_limit": max(MAX_FILE_BYTES, MAX_SOURCE_FILE_BYTES),
            "bounded_api": {"file_limit": MAX_TEXT_FILES, "per_file_byte_limit": MAX_FILE_BYTES},
            "exact_sha_archive": {"file_limit": MAX_SOURCE_FILES, "per_file_byte_limit": MAX_SOURCE_FILE_BYTES,
                                  "total_byte_limit": MAX_TOTAL_SOURCE_BYTES, "archive_byte_limit": MAX_ARCHIVE_BYTES},
            "selection_method": "Bounded API priority paths followed by sorted eligible paths; exact-SHA archive sources in sorted path order within existing archive file and byte limits. Overlapping paths are counted once.",
        }
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
