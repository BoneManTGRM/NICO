from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nico import repository_snapshot as snapshot_capture
from nico.full_assessment_ci_evidence import collect_ci_runtime_evidence
from nico.full_assessment_complexity_evidence import SOURCE_SUFFIXES, collect_complexity_evidence
from nico.hosted_assessment import (
    KNOWN_FILE_PATHS,
    MAX_FILE_BYTES,
    MAX_TEXT_FILES,
    GitHubAssessmentClient,
    collect_dependencies,
    should_fetch_path,
)
from nico.source_signal_analysis_v2 import analyze_source_signals
from nico.source_architecture_evidence_v1 import analyze_source_architecture
from nico.repository_profile_coverage_v1 import profile_coverage
from nico.storage import STORE, StorageAdapter

DEFAULT_TIMEFRAME_DAYS = 180
DEPENDENCY_MANIFEST_NAMES = {
    "requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
}
LOCKFILE_NAMES = {"Pipfile.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
DEPLOYMENT_NAMES = {"Dockerfile", "Procfile", "render.yaml", "railway.json", "railway.toml", "fly.toml", "vercel.json"}
WORKFLOW_COMMANDS = ["pytest", "npm test", "npm run lint", "npm run build", "next build", "eslint", "mypy", "ruff", "semgrep", "bandit"]


def _bounded_git_bytes(git_dir, environment, arguments, *, limit, deadline, data=None, checkpoint=None):
    """Read trusted Git output with a byte ceiling and one aggregate deadline."""
    if checkpoint is not None:
        checkpoint()
    if time.monotonic() >= deadline:
        raise ValueError("input_acquisition_timed_out")
    process = subprocess.Popen(
        ["git", "--no-replace-objects", "--no-lazy-fetch", *arguments], cwd=str(git_dir),
        env=environment, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
        shell=False, bufsize=0,
    )
    result = bytearray()
    pending = memoryview(data or b"")
    try:
        with selectors.DefaultSelector() as ready:
            os.set_blocking(process.stdout.fileno(), False)
            ready.register(process.stdout, selectors.EVENT_READ)
            if process.stdin is not None:
                if pending:
                    os.set_blocking(process.stdin.fileno(), False)
                    ready.register(process.stdin, selectors.EVENT_WRITE)
                else:
                    process.stdin.close()
            while ready.get_map():
                if checkpoint is not None:
                    checkpoint()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("input_acquisition_timed_out")
                for key, _ in ready.select(min(remaining, 0.1)):
                    if key.fileobj is process.stdout:
                        chunk = os.read(key.fd, min(65536, limit - len(result) + 1))
                        if not chunk:
                            ready.unregister(key.fileobj)
                        else:
                            result.extend(chunk)
                            if len(result) > limit:
                                raise ValueError("input_output_budget_exceeded")
                    else:
                        try:
                            count = os.write(key.fd, pending[:65536])
                        except BrokenPipeError:
                            count = len(pending)
                        pending = pending[count:]
                        if not pending:
                            ready.unregister(key.fileobj)
                            process.stdin.close()
            if process.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
                raise ValueError("input_git_read_failed")
        if checkpoint is not None:
            checkpoint()
        return bytes(result)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("input_acquisition_timed_out") from exc
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        process.stdout.close()
        if process.stdin is not None:
            process.stdin.close()


def materialize_exact_git_inputs(
    *, git_dir: Path, commit_sha: str,
    expected_tree_sha: str, inputs: dict[str, str], destination: Path,
    max_files: int, max_file_bytes: int, max_total_bytes: int, timeout_seconds: int,
    checkpoint=None,
) -> dict[str, Any]:
    """Materialize required raw blobs from an acquired Git store, without checkout.

    The caller owns the private destination parent and authorizes acquisition
    separately. This does not fetch, execute source, follow links or grant run
    authority. The input population is not an analyzed-target denominator.
    Existing report-text profiling remains a separate projection of Git bytes.
    """
    from pathlib import PurePosixPath
    import io

    if (not isinstance(commit_sha, str) or not snapshot_capture._EXACT_SHA_RE.fullmatch(commit_sha)
            or not isinstance(expected_tree_sha, str)
            or not snapshot_capture._EXACT_SHA_RE.fullmatch(expected_tree_sha)):
        raise ValueError("input_revision_or_tree_invalid")
    ceilings = ((max_files, 20000), (max_file_bytes, 16 * 1024 * 1024),
                (max_total_bytes, 150_000_000), (timeout_seconds, 300))
    if any(type(value) is not int or not 1 <= value <= maximum for value, maximum in ceilings):
        raise ValueError("input_budget_invalid")
    if not isinstance(inputs, dict) or not inputs or len(inputs) > max_files:
        raise ValueError("input_budget_exceeded")
    inputs = dict(inputs)
    for path, digest in inputs.items():
        if (not isinstance(path, str) or not path or len(path) > 1000
                or path.startswith("/") or ":" in path or "\\" in path
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
                or PurePosixPath(path).as_posix() != path
                or any(part in {".", "..", ".git"} for part in path.split("/"))
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("input_path_or_digest_invalid")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("input_destination_exists")
    parent = destination.parent.resolve(strict=True)
    owner = parent.stat()
    if owner.st_uid != os.getuid() or owner.st_mode & 0o022:
        raise ValueError("input_destination_parent_not_private")
    deadline = time.monotonic() + timeout_seconds
    environment = snapshot_capture._git_environment(parent)
    # This stage reads the already acquired object database only. Missing Git
    # objects must fail rather than silently invoking transport during handoff.
    environment["GIT_NO_LAZY_FETCH"] = "1"

    def git(*arguments, limit, data=None):
        return _bounded_git_bytes(git_dir, environment, arguments, limit=limit,
                                  deadline=deadline, data=data, checkpoint=checkpoint)

    identity = git("show", "-s", "--format=%H%x00%T", commit_sha, limit=200).strip().split(b"\0")
    if identity != [commit_sha.lower().encode(), expected_tree_sha.lower().encode()]:
        raise ValueError("input_revision_or_tree_mismatch")
    listing = git("ls-tree", "-r", "-z", "-l", commit_sha, limit=8 * 1024 * 1024)
    if not listing.endswith(b"\0"):
        raise ValueError("input_tree_listing_incomplete")
    entries = {}
    for row in listing.split(b"\0")[:-1]:
        try:
            metadata, raw_path = row.split(b"\t", 1)
            mode, kind, oid, size = metadata.split()
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("input_tree_listing_invalid") from exc
        if path in entries or not re.fullmatch(b"[0-9a-f]{40}", oid):
            raise ValueError("input_tree_listing_invalid")
        entries[path] = (mode, kind, oid, size)
    selected = []
    total = 0
    for path in sorted(inputs):
        if path not in entries:
            raise ValueError("input_required_path_missing")
        mode, kind, oid, size = entries[path]
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise ValueError("input_type_unsupported")
        if not size.isdigit():
            raise ValueError("input_blob_size_invalid")
        size = int(size)
        total += size
        if size > max_file_bytes or total > max_total_bytes:
            raise ValueError("input_budget_exceeded")
        selected.append((path, oid, size))
    raw = git("cat-file", "--batch", limit=total + len(selected) * 128,
              data=b"\n".join(oid for _, oid, _ in selected) + b"\n")
    stream = io.BytesIO(raw)
    with tempfile.TemporaryDirectory(prefix=".nico-inputs-", dir=parent) as temporary:
        stage = Path(temporary) / "inputs"
        stage.mkdir(mode=0o700)
        for path, oid, size in selected:
            if checkpoint is not None:
                checkpoint()
            if stream.readline() != oid + b" blob " + str(size).encode() + b"\n":
                raise ValueError("input_blob_header_mismatch")
            content = stream.read(size)
            if len(content) != size or stream.read(1) != b"\n":
                raise ValueError("input_blob_truncated")
            # Git's existing object format uses SHA1 for compatibility. The
            # separately frozen SHA256 below remains the content security check.
            actual_object = hashlib.sha1(b"blob " + str(size).encode() + b"\0" + content,
                                         usedforsecurity=False).hexdigest()
            if actual_object.encode() != oid or hashlib.sha256(content).hexdigest() != inputs[path]:
                raise ValueError("input_digest_mismatch")
            if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError("input_type_unsupported")
            output = stage / path
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with output.open("xb") as handle:
                handle.write(content)
            output.chmod(0o444)
        if stream.read(1):
            raise ValueError("input_blob_population_mismatch")
        if checkpoint is not None:
            checkpoint()
        if time.monotonic() >= deadline:
            raise ValueError("input_acquisition_timed_out")
        try:
            destination.mkdir(mode=0o700)  # exclusive reservation; never reuse caller data
        except FileExistsError as exc:
            raise ValueError("input_destination_exists") from exc
        try:
            os.replace(stage, destination)
        except BaseException:
            destination.rmdir()
            raise
    membership = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    return {"schema": "nico.exact_git_input_materialization.v1",
        "commit_sha": commit_sha.lower(), "tree_sha": expected_tree_sha.lower(),
        "inputs": inputs, "population_sha256": hashlib.sha256(membership).hexdigest(),
        "required_count": len(inputs), "materialized_count": len(inputs), "source_bytes": total,
        "analyzed_count": None, "authorized": False, "assessed_code_executed": False}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _short(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _id(prefix: str, run_id: str, repository: str, snapshot_id: str) -> str:
    digest = hashlib.sha256(f"{prefix}|{run_id}|{repository}|{snapshot_id}".encode()).hexdigest()[:20]
    return f"evidence_{prefix}_{digest}"


def _safe_note(label: str, error: Any) -> str:
    lowered = str(error or "").lower()
    if "429" in lowered or "rate" in lowered:
        return f"{label} was unavailable because the GitHub API rate limit was reached."
    if "401" in lowered or "403" in lowered:
        return f"{label} was unavailable because the GitHub credential or installation lacks required read access."
    if "404" in lowered:
        return f"{label} was unavailable through the authorized GitHub API scope."
    return f"{label} was unavailable through the GitHub API."


def _provider_access_observation(
    client: Any,
) -> tuple[bool, str, bool | None]:
    credential_used = getattr(client, "credential_used", None)
    access_mode = str(getattr(client, "access_mode", "") or "").strip()
    valid = (
        (access_mode == "anonymous_public" and credential_used is False)
        or (
            access_mode == "authenticated_read_only"
            and credential_used is True
        )
    )
    if not valid:
        return False, "", None
    return True, access_mode, credential_used


def _client_for_context(
    context: dict[str, Any],
    client: GitHubAssessmentClient | None,
) -> GitHubAssessmentClient:
    """Bind evidence acquisition to the access mode frozen at public intake."""

    if client is not None:
        return client
    active = GitHubAssessmentClient()
    if (
        str(context.get("provider_access_mode") or "").strip()
        == "anonymous_public"
        and context.get("provider_credential_used") is False
    ):
        active.headers = {
            key: value
            for key, value in active.headers.items()
            if str(key).casefold() != "authorization"
        }
        active.credential_used = False
        active.access_mode = "anonymous_public"
    return active


def _capability(
    capability: str,
    state: str,
    reason: str = "",
) -> dict[str, str]:
    return {
        "capability": capability,
        "state": state,
        "reason": _short(reason, 240),
    }


def _collection_capability(
    capability: str,
    values: list[dict[str, Any]],
    error: str | None,
    *,
    credential_used: bool,
    label: str,
) -> dict[str, str]:
    if error:
        lowered = str(error).casefold()
        if "429" in lowered or "rate" in lowered:
            state = "rate_limited"
        elif any(code in lowered for code in ("401", "403", "404")):
            state = (
                "unavailable_permission"
                if credential_used
                else "unavailable_authentication"
            )
        else:
            state = "collection_failed"
        return _capability(capability, state, _safe_note(label, error))
    if values:
        return _capability(capability, "supported")
    return _capability(capability, "supported_empty")


def _exact_source_identity(
    repository: str,
    commit_sha: str,
    tree_sha: str,
    tree_paths: list[str],
    retained_paths: list[str],
) -> tuple[str, list[str]]:
    if not (repository and commit_sha and tree_sha and tree_paths):
        return "", []
    material = json.dumps(
        {
            "provider": "github",
            "repository": repository,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "tree_paths": sorted(set(tree_paths)),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    fingerprint = "sha256:" + hashlib.sha256(material).hexdigest()
    locators = [
        (
            f"https://github.com/{quote(repository, safe='/')}/blob/"
            f"{quote(commit_sha, safe='')}/{quote(path, safe='/')}"
        )
        for path in sorted(set(retained_paths))[:MAX_TEXT_FILES]
    ]
    return fingerprint, locators


def _get_json(client: Any, repository: str, path: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
    return client.get_json(client.repo_url(repository, path), params)


def _contents(client: Any, repository: str, path: str, ref: str) -> tuple[Any | None, str | None]:
    suffix = f"/contents/{quote(path, safe='/')}" if path else "/contents"
    return _get_json(client, repository, suffix, {"ref": ref})


def _raw_file(client: Any, repository: str, path: str, ref: str) -> tuple[bytes | None, str | None]:
    value, error = _contents(client, repository, path, ref)
    if error:
        return None, error
    if not isinstance(value, dict) or value.get("type") != "file":
        return None, f"{path} is not a file at the captured commit."
    if int(value.get("size") or 0) > MAX_FILE_BYTES:
        return None, f"{path} exceeds the hosted text-inspection limit."
    try:
        raw = base64.b64decode(''.join((value.get("content") or "").split()), validate=True)
        if len(raw) > MAX_FILE_BYTES:
            return None, f"{path} exceeds the hosted text-inspection limit."
        return raw, None
    except Exception:
        return None, f"{path} could not be decoded at the captured commit."


def _text_file(client: Any, repository: str, path: str, ref: str) -> tuple[str | None, str | None]:
    raw, error = _raw_file(client, repository, path, ref)
    return (raw.decode('utf-8', errors='replace') if raw is not None else None), error


def _profile(client: Any, repository: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    commit_sha = str(snapshot.get("commit_sha") or "")
    tree_ref = str(snapshot.get("tree_sha") or commit_sha)
    tree_value, tree_error = _get_json(client, repository, f"/git/trees/{quote(tree_ref, safe='')}", {"recursive": "1"})
    tree = tree_value.get("tree") if isinstance(tree_value, dict) and isinstance(tree_value.get("tree"), list) else []
    root, root_error = _contents(client, repository, "", commit_sha)
    root_items = [str(item.get("name") or "") for item in root if isinstance(item, dict)] if isinstance(root, list) else []
    unavailable: list[str] = []
    if tree_error or not tree:
        unavailable.append(_safe_note("Captured-commit recursive file tree", tree_error))
    if root_error:
        unavailable.append(_safe_note("Captured-commit root listing", root_error))

    valid_entries = {}
    invalid_paths: set[str] = set()
    inventory_paths: set[str] = set()
    seen: set[str] = set()
    inventory_valid = True
    for item in tree:
        path = item.get("path") if isinstance(item, dict) else None
        if (not isinstance(path, str) or not path or path.startswith("/")
                or any(part in {"", ".", ".."} for part in path.split("/")) or "\x00" in path):
            inventory_valid = False
            continue
        if item.get("type") != "tree":
            inventory_paths.add(path)
        kind, mode, object_id = item.get("type"), item.get("mode"), item.get("sha")
        modes = {"blob": {"100644", "100755", "120000"}, "commit": {"160000"}, "tree": {"040000"}}
        valid = (path not in seen and isinstance(kind, str) and isinstance(mode, str)
                 and mode in modes.get(kind, set())
                 and isinstance(object_id, str) and snapshot_capture._SHA_RE.fullmatch(object_id)
                 and (kind != "blob" or (type(item.get("size")) is int and item["size"] >= 0)))
        seen.add(path)
        if not valid:
            inventory_valid = False
            invalid_paths.add(path)
            valid_entries.pop(path, None)
        elif path not in invalid_paths:
            valid_entries[path] = item
    blobs = [item for item in valid_entries.values() if item["type"] == "blob"]
    submodules = [{"path": str(item["path"]), "commit_sha": item.get("sha")}
                  for item in valid_entries.values() if item["type"] == "commit"]
    symlink_paths = {str(item["path"]) for item in blobs if item.get("mode") == "120000"}
    lfs_entries: list[dict[str, Any]] = []
    sizes = {str(item["path"]): int(item.get("size") or 0) for item in blobs}
    from nico.full_source_archive_profile_v1 import _eligible
    candidates = [path for path in KNOWN_FILE_PATHS if path in sizes]
    candidates.extend(path for path in sorted(sizes) if path not in candidates
                      and (should_fetch_path(path, sizes[path]) or (_eligible(path) and sizes[path] <= MAX_FILE_BYTES)))
    files: dict[str, str] = {}
    raw_records: dict[str, dict] = {}
    from nico.snapshot_execution_inputs import raw_input_record, matches_tree
    unavailable_paths: list[str] = sorted(invalid_paths | symlink_paths | {row["path"] for row in submodules})
    from nico.full_source_archive_profile_v1 import lfs_pointer_entry
    for path in candidates[:MAX_TEXT_FILES]:
        if path in symlink_paths:
            continue
        raw, error = _raw_file(client, repository, path, commit_sha)
        if raw is not None:
            text = raw.decode('utf-8', errors='replace')
            pointer = lfs_pointer_entry(path, text)
            if pointer is not None:
                lfs_entries.append(pointer)
                unavailable_paths.append(path)
            else:
                files[path] = text
                record = raw_input_record(raw)
                if matches_tree(record, valid_entries[path]):
                    raw_records[path] = record
        else:
            unavailable_paths.append(path)
            unavailable.append(_safe_note(f"Captured-commit file {path}", error))
    return {
        "files": files,
        "raw_input_records": raw_records,
        "raw_input_selected_paths": sorted(candidates[:MAX_TEXT_FILES]),
        "raw_blob_inventory": valid_entries,
        "tree_paths": sorted(inventory_paths),
        "root_items": root_items,
        "unavailable": sorted(set(unavailable)),
        "unavailable_paths": sorted(unavailable_paths),
        "submodule_entries": submodules,
        "symlink_paths_not_followed": sorted(symlink_paths),
        "lfs_pointer_entries": lfs_entries,
        "size_excluded_paths": sorted(path for path, size in sizes.items() if size > MAX_FILE_BYTES),
        "tree_sha": (
            str(tree_value.get("sha") or "").strip().lower()
            if isinstance(tree_value, dict)
            else ""
        ),
        "tree_truncated": (
            bool(tree_value.get("truncated"))
            if isinstance(tree_value, dict)
            else False
        ),
        "tree_collection_succeeded": (
            tree_error is None
            and inventory_valid
            and isinstance(tree_value, dict)
            and isinstance(tree_value.get("tree"), list)
        ),
    }


def _public_git_profile(
    repository: str,
    commit_sha: str,
    expected_tree_sha: str,
) -> tuple[dict[str, Any] | None, str]:
    """Read bounded exact-revision source evidence without API quota or credentials."""

    if not snapshot_capture._SAFE_REPOSITORY_RE.fullmatch(repository):
        return None, "public_git_invalid_repository"
    if not snapshot_capture._EXACT_SHA_RE.fullmatch(commit_sha):
        return None, "public_git_invalid_commit_sha"
    if expected_tree_sha and not snapshot_capture._SHA_RE.fullmatch(expected_tree_sha):
        return None, "public_git_invalid_tree_sha"

    repository_url = f"https://github.com/{repository}.git"
    try:
        with tempfile.TemporaryDirectory(prefix="nico-public-evidence-") as temporary:
            workspace = Path(temporary)
            git_dir = workspace / "repository.git"
            git_dir.mkdir(mode=0o700)
            environment = snapshot_capture._git_environment(workspace)

            initialized = snapshot_capture._git_init_bare(
                git_dir,
                environment,
                runner=subprocess.run,
            )
            if initialized.returncode != 0:
                return None, "public_git_initialize_failed"
            snapshot_capture._configure_public_origin(git_dir, repository_url)
            fetched = snapshot_capture._git_fetch_exact_sha(
                git_dir,
                commit_sha,
                environment,
                runner=subprocess.run,
            )
            if fetched.returncode != 0:
                return None, "public_git_exact_sha_fetch_failed"
            from nico import scanner_worker as scanner_base

            history_observation = scanner_base.repository_size_observation(git_dir, bare=True)
            if history_observation["exceeded_limits"]:
                return None, "public_git_history_size_limit_exceeded"
            if not history_observation["inventory_complete"]:
                return None, "public_git_history_size_unverified"

            identity = subprocess.run(
                ["git", "show", "-s", "--format=%H%x00%T", "FETCH_HEAD"],
                cwd=str(git_dir),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                shell=False,
                env=environment,
            )
            identity_parts = identity.stdout.rstrip("\n").split("\x00", 1)
            if identity.returncode != 0 or len(identity_parts) != 2:
                return None, "public_git_commit_description_failed"
            actual_commit, actual_tree = (
                identity_parts[0].strip().lower(),
                identity_parts[1].strip().lower(),
            )
            if actual_commit != commit_sha.lower():
                return None, "public_git_commit_mismatch"
            if not snapshot_capture._SHA_RE.fullmatch(actual_tree):
                return None, "public_git_tree_sha_invalid"
            if expected_tree_sha and actual_tree != expected_tree_sha.lower():
                return None, "public_git_tree_mismatch"

            listing = subprocess.run(
                ["git", "ls-tree", "-r", "-z", "-l", "FETCH_HEAD"],
                cwd=str(git_dir),
                capture_output=True,
                timeout=30,
                check=False,
                shell=False,
                env=environment,
            )
            if listing.returncode != 0:
                return None, "public_git_tree_listing_failed"

            sizes: dict[str, int] = {}
            blob_ids: dict[str, str] = {}
            symlink_paths: set[str] = set()
            submodules: list[dict[str, str]] = []
            inventory_paths: set[str] = set()
            inventory_complete = True
            for raw_record in listing.stdout.split(b"\x00"):
                if not raw_record:
                    continue
                if b"\t" not in raw_record:
                    inventory_complete = False
                    continue
                metadata, raw_path = raw_record.split(b"\t", 1)
                fields = metadata.split()
                if len(fields) != 4:
                    inventory_complete = False
                    continue
                try:
                    path = raw_path.decode("utf-8", errors="strict")
                    object_id = fields[2].decode("ascii")
                except (UnicodeDecodeError, ValueError):
                    inventory_complete = False
                    continue
                if not path or path in inventory_paths or not snapshot_capture._SHA_RE.fullmatch(object_id):
                    inventory_complete = False
                    continue
                inventory_paths.add(path)
                if fields[0] == b"160000" and fields[1] == b"commit":
                    submodules.append({"path": path, "commit_sha": object_id})
                    continue
                if fields[1] != b"blob" or fields[0] not in {b"100644", b"100755", b"120000"}:
                    inventory_complete = False
                    continue
                try:
                    size = int(fields[3])
                except ValueError:
                    inventory_complete = False
                    continue
                if path and "\x00" not in path and size >= 0:
                    sizes[path] = size
                    blob_ids[path] = object_id
                    if fields[0] == b'120000':
                        symlink_paths.add(path)
                else:
                    inventory_complete = False

            candidates = [path for path in KNOWN_FILE_PATHS if path in sizes]
            candidates.extend(
                path
                for path in sorted(sizes)
                if path not in candidates and should_fetch_path(path, sizes[path])
            )
            files: dict[str, str] = {}
            raw_records: dict[str, dict] = {}
            from nico.snapshot_execution_inputs import raw_input_record
            unavailable: list[str] = []
            unavailable_paths: list[str] = []
            from nico import full_source_archive_profile_v1 as source_policy
            lfs_entries: list[dict[str, Any]] = []
            selected = {path for path in candidates[:MAX_TEXT_FILES]
                        if sizes[path] <= MAX_FILE_BYTES and path not in symlink_paths}
            source_paths: list[str] = []
            source_bytes = 0
            size_excluded: list[str] = []
            limit_excluded: list[str] = []
            for path in sorted(sizes):
                if not source_policy._eligible(path) or path in symlink_paths:
                    continue
                if sizes[path] > source_policy.MAX_SOURCE_FILE_BYTES:
                    size_excluded.append(path)
                    continue
                if len(source_paths) >= source_policy.MAX_SOURCE_FILES or source_bytes + sizes[path] > source_policy.MAX_TOTAL_SOURCE_BYTES:
                    limit_excluded.append(path)
                    continue
                source_paths.append(path)
                source_bytes += sizes[path]
            selected.update(source_paths)
            ordered = sorted(selected)
            if ordered:
                # Object IDs from the verified tree avoid newline/path ambiguity
                # and process-per-file overhead; requested byte sizes are bounded.
                batch = subprocess.run(['git', 'cat-file', '--batch'], cwd=str(git_dir),
                    input=('\n'.join(blob_ids[path] for path in ordered) + '\n').encode('ascii'),
                    capture_output=True, timeout=90, check=False, shell=False, env=environment)
                import io
                stream = io.BytesIO(batch.stdout if batch.returncode == 0 else b'')
                for path in ordered:
                    header = stream.readline().split()
                    if header != [blob_ids[path].encode('ascii'), b'blob', str(sizes[path]).encode('ascii')]:
                        break
                    content = stream.read(sizes[path])
                    if len(content) != sizes[path] or stream.read(1) != b'\n':
                        break
                    text = content.decode('utf-8', errors='replace')
                    pointer = source_policy.lfs_pointer_entry(path, text)
                    if pointer is not None:
                        lfs_entries.append(pointer)
                    else:
                        files[path] = text
                        record = raw_input_record(content)
                        if record['blob_sha'] == blob_ids[path]:
                            raw_records[path] = record
                unavailable_paths = sorted(selected - set(files))
                unavailable = [f'Exact public Git snapshot file {path} could not be read.' for path in unavailable_paths]

            unavailable_paths = sorted(set(unavailable_paths) | symlink_paths | {row["path"] for row in submodules})
            paths = sorted(inventory_paths)
            return {
                "files": files,
                "raw_input_records": raw_records,
                "raw_input_selected_paths": ordered,
                "tree_paths": paths,
                "root_items": sorted({path.split("/", 1)[0] for path in paths}),
                "unavailable": unavailable,
                "unavailable_paths": unavailable_paths,
                "submodule_entries": submodules,
                "symlink_paths_not_followed": sorted(symlink_paths),
                "lfs_pointer_entries": lfs_entries,
                "git_history_observation": history_observation,
                "size_excluded_paths": sorted(set(size_excluded) | {path for path in candidates[:MAX_TEXT_FILES] if sizes[path] > MAX_FILE_BYTES and path not in files}),
                "source_profile": {"source_files_loaded": len(set(source_paths) & set(files)),
                    "source_bytes_loaded": sum(sizes[path] for path in source_paths if path in files),
                    "limit_excluded_paths": limit_excluded, "size_excluded_paths": size_excluded,
                    "symlink_paths_not_followed": sorted(symlink_paths), "snapshot_commit_sha": actual_commit,
                    "acquisition_method": "exact_tree_git_blob_batch"},
                "profile_limits": {"file_limit": MAX_TEXT_FILES + source_policy.MAX_SOURCE_FILES,
                    "per_file_byte_limit": max(MAX_FILE_BYTES, source_policy.MAX_SOURCE_FILE_BYTES),
                    "source_total_byte_limit": source_policy.MAX_TOTAL_SOURCE_BYTES,
                    "source_file_limit": source_policy.MAX_SOURCE_FILES,
                    "selection_method": "Bounded priority metadata and sorted exact-revision source blobs within the existing full-source file and byte budgets."},
                "tree_sha": actual_tree,
                "tree_truncated": False,
                "tree_collection_succeeded": inventory_complete,
                "public_git_fallback_used": True,
            }, ""
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, "public_git_execution_failed"


def _workflows(
    client: Any,
    repository: str,
    snapshot: dict[str, Any],
    paths: list[str],
    retained_files: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    commit_sha = str(snapshot.get("commit_sha") or "")
    workflow_paths = [path for path in paths if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))]
    retained = retained_files or {}
    values: dict[str, str] = {}
    unavailable: list[str] = []
    for path in workflow_paths:
        if path in retained:
            values[path] = retained[path]
            continue
        text, error = _text_file(client, repository, path, commit_sha)
        if text is None:
            unavailable.append(_safe_note(f"Captured-commit workflow {path}", error))
        else:
            values[path] = text
    if not workflow_paths:
        unavailable.append("No workflow files were present in the captured repository snapshot.")
    return values, unavailable


def _bounded_commits(commits: list[dict[str, Any]], captured_at: datetime) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in commits:
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        date = _parse_iso(author.get("date"))
        if date and date <= captured_at:
            result.append(item)
    return result


def _bounded_pulls(pulls: list[dict[str, Any]], captured_at: datetime) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in pulls:
        updated = _parse_iso(item.get("updated_at"))
        if updated and updated <= captured_at:
            result.append(item)
    return result


def _workflow_summary(workflows: dict[str, str], runs: list[dict[str, Any]], ci: dict[str, Any], snapshot_sha: str) -> dict[str, Any]:
    combined = "\n".join(workflows.values()).lower()
    jobs = ci.get("job_evidence") if isinstance(ci.get("job_evidence"), dict) else {}
    deployments = ci.get("deployment_evidence") if isinstance(ci.get("deployment_evidence"), dict) else {}
    terminal = [item for item in runs if item.get("conclusion")]
    return {
        "workflow_files": sorted(workflows),
        "workflow_file_count": len(workflows),
        "workflow_configuration_snapshot_sha": snapshot_sha,
        "workflow_run_count": len(runs),
        "successful_runs": sum(1 for item in terminal if item.get("conclusion") == "success"),
        "non_success_runs": sum(1 for item in terminal if item.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"}),
        "runs_matching_snapshot_sha": sum(1 for item in runs if str(item.get("head_sha") or "").lower() == snapshot_sha.lower()),
        "commands_detected": [command for command in WORKFLOW_COMMANDS if command in combined],
        "explicit_permissions_present": "permissions:" in combined,
        "secret_references_present": "secrets." in combined,
        "runtime_evidence_status": ci.get("status") or "unavailable",
        "configuration_controls": ci.get("configuration_controls") or {},
        "job_evidence": jobs,
        "deployment_evidence": deployments,
        "jobs_observed": int(jobs.get("jobs_observed") or 0),
        "successful_jobs": int(jobs.get("successful_jobs") or 0),
        "non_success_jobs": int(jobs.get("non_success_jobs") or 0),
        "job_success_rate": jobs.get("job_success_rate"),
        "average_job_duration_seconds": jobs.get("average_job_duration_seconds"),
        "median_job_duration_seconds": jobs.get("median_job_duration_seconds"),
        "deployments_observed": int(deployments.get("deployments_observed") or 0),
        "successful_deployments": int(deployments.get("successful_deployments") or 0),
        "non_success_deployments": int(deployments.get("non_success_deployments") or 0),
        "ci_runtime_guardrail": "Workflow configuration is bound to the captured commit. Run, job, and deployment evidence is historical operational evidence observed through capture time and may include other commits.",
    }


def _persist(bundle: dict[str, Any], store: StorageAdapter, filename: str) -> None:
    encoded = json.dumps(bundle, sort_keys=True, default=str).encode()
    store.put("evidence_items", str(bundle["evidence_id"]), {
        "evidence_id": bundle["evidence_id"], "customer_id": bundle.get("customer_id") or "default_customer",
        "project_id": bundle.get("project_id") or "default_project", "run_id": bundle.get("run_id") or "",
        "filename": filename, "content_type": "application/json", "size_bytes": len(encoded),
        "source": bundle.get("source") or "github_api_read_only", "repository": bundle.get("repository") or "",
        "evidence": bundle,
    })


def collect_snapshot_repository_evidence(
    context: dict[str, Any], snapshot: dict[str, Any], *,
    client: GitHubAssessmentClient | None = None, store: StorageAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect code evidence from one commit and label operational history separately."""

    active_store = _store(store)
    run_id, repository = str(context.get("run_id") or ""), str(context.get("repository") or "")
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    evidence_id = _id("snapshot_repo", run_id, repository, snapshot_id)
    complexity_id = _id("snapshot_complexity", run_id, repository, snapshot_id)
    existing = active_store.get("evidence_items", evidence_id)
    existing_complexity = active_store.get("evidence_items", complexity_id)
    if isinstance(existing, dict) and isinstance(existing.get("evidence"), dict) and isinstance(existing_complexity, dict) and isinstance(existing_complexity.get("evidence"), dict):
        bundle, complexity = dict(existing["evidence"]), dict(existing_complexity["evidence"])
        bundle["idempotent_reuse"] = complexity["idempotent_reuse"] = True
        return bundle, complexity

    if not (snapshot.get("status") == "attached" and snapshot.get("run_id") == run_id and snapshot.get("repository") == repository and snapshot.get("commit_sha")):
        unavailable = {
            "status": "unavailable", "evidence_id": evidence_id, "run_id": run_id, "repository": repository,
            "customer_id": context.get("customer_id") or "default_customer", "project_id": context.get("project_id") or "default_project",
            "snapshot_id": snapshot_id, "source": "github_api_read_only",
            "unavailable_data_notes": ["Snapshot-bound repository evidence requires an attached snapshot with matching run and repository identity."],
            "idempotent_reuse": False, "human_review_required": True,
        }
        return unavailable, {**unavailable, "evidence_id": complexity_id, "source": "github_api_snapshot_bound_complexity"}

    github = _client_for_context(context, client)
    (
        provider_access_observed,
        access_mode,
        credential_used,
    ) = _provider_access_observation(github)
    if not provider_access_observed:
        unavailable = {
            "status": "unavailable",
            "evidence_id": evidence_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": context.get("customer_id") or "default_customer",
            "project_id": context.get("project_id") or "default_project",
            "snapshot_id": snapshot_id,
            "source": "github_api_read_only",
            "unavailable_data_notes": [
                "The GitHub collection client did not expose a valid safe access observation."
            ],
            "idempotent_reuse": False,
            "human_review_required": True,
        }
        return unavailable, {
            **unavailable,
            "evidence_id": complexity_id,
            "source": "github_api_snapshot_bound_complexity",
        }

    snapshot_access_observed = snapshot.get("provider_access_observed") is True
    if snapshot_access_observed and (
        snapshot.get("access_mode") != access_mode
        or snapshot.get("credential_used") is not credential_used
    ):
        unavailable = {
            "status": "unavailable",
            "evidence_id": evidence_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": context.get("customer_id") or "default_customer",
            "project_id": context.get("project_id") or "default_project",
            "snapshot_id": snapshot_id,
            "source": "github_api_read_only",
            "provider_access_binding_consistent": False,
            "unavailable_data_notes": [
                "The GitHub access mode changed after the immutable snapshot was captured."
            ],
            "idempotent_reuse": False,
            "human_review_required": True,
        }
        return unavailable, {
            **unavailable,
            "evidence_id": complexity_id,
            "source": "github_api_snapshot_bound_complexity",
        }

    captured_at = _parse_iso(snapshot.get("captured_at")) or datetime.now(timezone.utc)
    timeframe_days = max(30, min(int(context.get("timeframe_days") or DEFAULT_TIMEFRAME_DAYS), 365))
    since = captured_at - timedelta(days=timeframe_days)
    explicit_anonymous_binding = (
        str(context.get("provider_access_mode") or "").strip()
        == "anonymous_public"
        and context.get("provider_credential_used") is False
    )
    public_profile = None
    public_profile_error = ""
    if explicit_anonymous_binding:
        public_profile, public_profile_error = _public_git_profile(
            repository,
            str(snapshot.get("commit_sha") or "").strip().lower(),
            str(snapshot.get("tree_sha") or "").strip().lower(),
        )
    profile = public_profile or _profile(github, repository, snapshot)
    api_profile_notes = list(profile.get("unavailable") or [])
    if (
        access_mode == "anonymous_public"
        and credential_used is False
        and profile.get("tree_collection_succeeded") is not True
    ):
        if not explicit_anonymous_binding:
            public_profile, public_profile_error = _public_git_profile(
                repository,
                str(snapshot.get("commit_sha") or "").strip().lower(),
                str(snapshot.get("tree_sha") or "").strip().lower(),
            )
        if public_profile is not None:
            profile = public_profile
            profile["unavailable"] = sorted(
                {
                    *api_profile_notes,
                    *(profile.get("unavailable") or []),
                    (
                        "Required source evidence was acquired from credential-free "
                        "exact-SHA Git because GitHub API tree collection was unavailable."
                    ),
                }
            )
        else:
            profile["unavailable"] = sorted(
                {
                    *api_profile_notes,
                    "Credential-free exact-SHA Git source fallback was unavailable "
                    f"({public_profile_error}).",
                }
            )
    elif public_profile is not None:
        profile["unavailable"] = sorted(
            {
                *(profile.get("unavailable") or []),
                (
                    "Required source evidence was acquired from credential-free "
                    "exact-SHA Git to preserve the anonymous public access binding "
                    "without depending on GitHub API object-read quota."
                ),
            }
        )
    files = profile["files"]
    workflows, workflow_unavailable = _workflows(
        github,
        repository,
        snapshot,
        profile["tree_paths"],
        files,
    )
    commits, commit_error = github.get_commits(repository, _iso(since))
    pulls, pull_error = github.get_pulls(repository, since)
    runs, run_error = github.get_workflow_runs(repository, _iso(since))
    bounded_commits, bounded_pulls = _bounded_commits(commits, captured_at), _bounded_pulls(pulls, captured_at)
    bounded_runs = [item for item in runs if (_parse_iso(item.get("created_at")) or captured_at) <= captured_at]
    ci = collect_ci_runtime_evidence(github, repository, workflows, bounded_runs)
    file_scan, dependencies = analyze_source_signals(files), collect_dependencies(files)
    paths = profile["tree_paths"]
    source_paths = [path for path in paths if path.lower().endswith(SOURCE_SUFFIXES) and not path.startswith("tests/") and "test" not in path.rsplit("/", 1)[-1].lower()]
    notes = list(profile["unavailable"]) + workflow_unavailable + list(ci.get("unavailable_data_notes") or [])
    for label, error in (("Commit history", commit_error), ("Pull-request history", pull_error), ("Workflow-run history", run_error)):
        if error:
            notes.append(_safe_note(label, error))

    snapshot_sha = str(snapshot.get("commit_sha") or "")
    tree_sha = str(
        profile.get("tree_sha")
        or snapshot.get("tree_sha")
        or ""
    ).strip().lower()
    source_fingerprint, exact_source_locators = _exact_source_identity(
        repository,
        snapshot_sha,
        tree_sha,
        paths,
        list(files),
    )
    required_source_evidence_complete = bool(
        snapshot_sha
        and paths
        and source_fingerprint
        and exact_source_locators
        and profile.get("tree_collection_succeeded") is True
        and profile.get("tree_truncated") is not True
    )
    pagination_limitation = (
        "GitHub operational collections are bounded to one provider page; "
        "complete Link-header pagination proof was not retained."
    )
    if profile.get("tree_truncated") is True:
        notes.append(
            "The GitHub recursive source tree was truncated and was not treated "
            "as complete required source evidence."
        )
    notes.append(pagination_limitation)

    rate_limited = any(
        "rate limit" in str(value or "").casefold()
        or "429" in str(value or "").casefold()
        for value in (
            commit_error,
            pull_error,
            run_error,
            *notes,
            *(ci.get("unavailable_data_notes") or []),
        )
    )
    job_evidence = (
        ci.get("job_evidence")
        if isinstance(ci.get("job_evidence"), dict)
        else {}
    )
    deployment_evidence = (
        ci.get("deployment_evidence")
        if isinstance(ci.get("deployment_evidence"), dict)
        else {}
    )
    if not bounded_runs:
        ci_job_capability = _capability("ci_jobs", "supported_empty")
    elif job_evidence.get("status") == "complete":
        ci_job_capability = _capability("ci_jobs", "supported")
    elif job_evidence.get("status") == "partial":
        ci_job_capability = _capability(
            "ci_jobs",
            "supported_limited",
            "Some workflow-job evidence was unavailable.",
        )
    else:
        ci_job_capability = _capability(
            "ci_jobs",
            "collection_failed",
            "Workflow-job evidence could not be collected.",
        )

    deployment_status = str(deployment_evidence.get("status") or "")
    if deployment_status == "complete":
        deployment_capability = _capability("deployments", "supported")
    elif deployment_status == "partial":
        deployment_capability = _capability(
            "deployments",
            "supported_limited",
            "Some deployment status evidence was unavailable.",
        )
    elif deployment_status == "not_observed":
        deployment_capability = _capability("deployments", "supported_empty")
    else:
        deployment_capability = _capability(
            "deployments",
            "collection_failed",
            "GitHub deployment evidence could not be collected.",
        )

    environments = list(deployment_evidence.get("environments") or [])
    if deployment_status == "unavailable":
        environment_capability = _capability(
            "environments",
            "collection_failed",
            "GitHub environment evidence could not be collected.",
        )
    elif environments:
        environment_capability = _capability("environments", "supported")
    else:
        environment_capability = _capability("environments", "supported_empty")

    if profile.get("tree_collection_succeeded") is not True:
        tree_capability = _capability(
            "tree",
            "collection_failed",
            "The immutable recursive source tree could not be collected.",
        )
    elif profile.get("tree_truncated") is True:
        tree_capability = _capability(
            "tree",
            "supported_limited",
            "The provider returned a truncated recursive source tree.",
        )
    elif paths:
        tree_capability = _capability("tree", "supported")
    else:
        tree_capability = _capability(
            "tree",
            "supported_empty",
            "The immutable repository source tree was empty.",
        )

    if files:
        blob_capability = _capability("blobs", "supported")
    elif not paths and profile.get("tree_collection_succeeded") is True:
        blob_capability = _capability("blobs", "supported_empty")
    else:
        blob_capability = _capability(
            "blobs",
            "collection_failed",
            "No retained text source object was available for assessment.",
        )

    provider_capability_states = [
        _capability("repository", "supported"),
        _collection_capability(
            "commits", bounded_commits, commit_error,
            credential_used=bool(credential_used), label="Commit history",
        ),
        _capability(
            "branches", "supported_limited",
            "Only the immutable default-branch identity was retained.",
        ),
        tree_capability,
        blob_capability,
        _capability("tags", "not_assessed"),
        _collection_capability(
            "change_requests", bounded_pulls, pull_error,
            credential_used=bool(credential_used), label="Pull-request history",
        ),
        _collection_capability(
            "ci_runs", bounded_runs, run_error,
            credential_used=bool(credential_used), label="Workflow-run history",
        ),
        ci_job_capability,
        environment_capability,
        deployment_capability,
        _capability("work_items", "not_assessed"),
        _capability("releases", "not_assessed"),
        _capability(
            "source_links",
            "supported" if exact_source_locators else "collection_failed",
            "" if exact_source_locators else "No exact-source locator was retained.",
        ),
    ]

    bundle = {
        "status": "attached", "evidence_id": evidence_id, "run_id": run_id, "repository": repository,
        "customer_id": context.get("customer_id") or "default_customer", "project_id": context.get("project_id") or "default_project",
        "source": "github_api_snapshot_bound_read_only", "authorization_scope": context.get("authorization_scope") or "repository assessment only",
        "repository_provider": "github",
        "repository_provider_instance": "github.com",
        "provider_access_observed": True,
        "provider_access_binding_consistent": True,
        "provider_access_mode": access_mode,
        "provider_credential_used": credential_used,
        "required_source_evidence_complete": required_source_evidence_complete,
        "provider_pagination_complete": False,
        "provider_rate_limit_state": {
            "limited": rate_limited,
            "reason": (
                "GitHub API rate limiting affected one or more evidence modules."
                if rate_limited
                else ""
            ),
        },
        "provider_collection_limitations": sorted(
            {str(note) for note in notes if str(note).strip()}
        ),
        "required_source_acquisition": (
            "credential_free_exact_sha_git"
            if profile.get("public_git_fallback_used") is True
            else "github_api_exact_revision"
        ),
        "provider_source_fingerprint": source_fingerprint,
        "exact_source_locators": exact_source_locators,
        "exact_source_locator_count": len(exact_source_locators),
        "assessment_snapshot_id": snapshot_id,
        "provider_capability_states": provider_capability_states,
        "timeframe_days": timeframe_days, "snapshot_id": snapshot_id, "snapshot_commit_sha": snapshot_sha,
        "snapshot_tree_sha": tree_sha, "snapshot_captured_at": snapshot.get("captured_at") or "",
        "code_evidence_scope": "File, manifest, workflow-configuration, executable code-signal, and complexity evidence is read from the exact captured commit.",
        "operational_evidence_scope": "Commit, PR, workflow-run, job, and deployment history is time-window evidence observed through capture time and is not exact-commit code evidence unless explicitly matched by SHA.",
        "repository_metadata": {"full_name": repository, "default_branch": snapshot.get("default_branch") or "", "visibility": snapshot.get("repository_visibility") or "unknown", "pushed_at": snapshot.get("repository_pushed_at") or "", "commit_sha": snapshot_sha, "tree_sha": snapshot.get("tree_sha") or ""},
        "file_evidence": {"files_profiled": len(files), "tree_paths_seen": len(paths), "sampled_paths": sorted(files)[:40], "top_level_items": sorted(profile["root_items"])[:40], "snapshot_commit_sha": snapshot_sha},
        "architecture_evidence": {"source_file_count": len(source_paths), "test_path_count": sum("test" in path.lower() for path in paths), "documentation_path_count": sum(path.lower().endswith(".md") or path.startswith("docs/") for path in paths), "deployment_manifests": sorted(path for path in paths if path.rsplit("/", 1)[-1] in DEPLOYMENT_NAMES)[:20], "top_level_directories": sorted(item for item in profile["root_items"] if "." not in item)[:30], "snapshot_commit_sha": snapshot_sha},
        "dependency_evidence": {"manifest_paths": sorted(path for path in files if path.rsplit("/", 1)[-1] in DEPENDENCY_MANIFEST_NAMES), "lockfile_paths": sorted(path for path in files if path.rsplit("/", 1)[-1] in LOCKFILE_NAMES), "dependency_entries": len(dependencies), "ecosystems": sorted({str(item.get("ecosystem") or "unknown") for item in dependencies}), "snapshot_commit_sha": snapshot_sha},
        "activity_evidence": {"status": "time_window_operational_evidence", "captured_through": _iso(captured_at), "commits_returned": len(bounded_commits), "pull_requests_returned": len(bounded_pulls), "merged_pull_requests": sum(bool(item.get("merged_at")) for item in bounded_pulls), "open_pull_requests": sum(item.get("state") == "open" for item in bounded_pulls), "sample_commits": [{"sha": str(item.get("sha") or "")[:12], "date": ((item.get("commit") or {}).get("author") or {}).get("date") or "", "message": _short((item.get("commit") or {}).get("message"), 160)} for item in bounded_commits[:10]], "sample_pull_requests": [{"number": item.get("number"), "state": item.get("state") or "unknown", "merged": bool(item.get("merged_at")), "updated_at": item.get("updated_at") or "", "title": _short(item.get("title"), 160)} for item in bounded_pulls[:10]]},
        "workflow_evidence": _workflow_summary(workflows, bounded_runs, ci, snapshot_sha),
        "code_signal_evidence": {
            "todo_fixme_security_notes": len(file_scan.get("todos") or []),
            "risk_pattern_hits": len(file_scan.get("risks") or []),
            "risk_records": list(file_scan.get("risk_records") or [])[:50],
            "excluded_non_production_risk_count": len(file_scan.get("excluded_non_production_risks") or []),
            "potential_secret_pattern_hits": len(file_scan.get("secrets") or []),
            "verified_example_placeholder_secret_count": len(file_scan.get("verified_example_placeholder_secrets") or []),
            "test_files_profiled": len(file_scan.get("test_paths") or []),
            "documentation_files_profiled": len(file_scan.get("docs") or []),
            "analysis_version": file_scan.get("analysis_version"),
            "executable_source_only": file_scan.get("executable_source_only") is True,
            "comments_and_strings_excluded": file_scan.get("comments_and_strings_excluded") is True,
            "snapshot_commit_sha": snapshot_sha,
        },
        "unavailable_data_notes": sorted({str(note) for note in notes if str(note).strip()}),
        "retention_note": "Only summarized repository evidence and bounded sampled-file analysis are retained; credentials and raw CI logs are not retained.",
        "idempotent_reuse": False, "human_review_required": True,
    }
    from nico.snapshot_execution_inputs import execution_input_manifest
    bundle['execution_input_manifest'] = execution_input_manifest(profile, snapshot)
    bundle["architecture_evidence"]["source_observation"] = analyze_source_architecture(
        files, run_id=run_id, repository=repository, commit_sha=snapshot_sha, snapshot_id=snapshot_id,
    )
    measured = collect_complexity_evidence(files)
    coverage = profile_coverage(profile, measured)
    bundle["file_evidence"]["profile_coverage"] = coverage
    complexity = {
        **measured, "profile_coverage": coverage, "evidence_id": complexity_id, "run_id": run_id, "repository": repository,
        "customer_id": bundle["customer_id"], "project_id": bundle["project_id"], "source": "github_api_snapshot_bound_complexity",
        "authorization_scope": bundle["authorization_scope"], "snapshot_id": snapshot_id, "snapshot_commit_sha": snapshot_sha,
        "snapshot_tree_sha": snapshot.get("tree_sha") or "", "profiled_file_count": len(files), "profile_unavailable_count": len(profile["unavailable"]),
        "idempotent_reuse": False, "human_review_required": True,
        "guardrail": "Complexity measurements cover only readable sampled source files from the exact captured commit.",
    }
    if profile["unavailable"]:
        complexity["unavailable_data_notes"] = sorted(set(list(complexity.get("unavailable_data_notes") or []) + [f"{len(profile['unavailable'])} captured-commit profile item(s) were unavailable; complexity coverage is limited to readable sampled files."]))
    _persist(bundle, active_store, "snapshot-repository-evidence.json")
    _persist(complexity, active_store, "snapshot-complexity-evidence.json")
    active_store.audit("assessment.snapshot_repository_evidence_collected", {"run_id": run_id, "repository": repository, "snapshot_id": snapshot_id, "snapshot_commit_sha": snapshot_sha, "files_profiled": len(files), "workflow_files": len(workflows), "complexity_files": complexity.get("files_analyzed") or 0}, customer_id=bundle["customer_id"], project_id=bundle["project_id"])
    return bundle, complexity
