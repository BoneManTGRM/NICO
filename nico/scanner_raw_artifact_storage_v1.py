"""Immutable scanner bytes on NICO's existing private PostgreSQL connection.

The generic STORE JSON table map deliberately does not expose this table. Reads
never create tables, migrate legacy files, change assessments or execute tools.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any
import zlib

VERSION = "nico.scanner-raw-artifact-storage.v1"
SCANNER_ARTIFACT_SCHEMA = """
CREATE TABLE IF NOT EXISTS scanner_raw_artifacts (
  artifact_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  scan_id TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  repository TEXT NOT NULL,
  commit_sha TEXT NOT NULL,
  scanner_name TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL,
  gzip_sha256 TEXT NOT NULL,
  gzip_blob BYTEA NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE (scan_id, scanner_name)
);
"""
BINDING_FIELDS = ("run_id", "scan_id", "customer_id", "project_id", "repository", "commit_sha", "scanner_name")
_SHA = re.compile(r"[a-fA-F0-9]{64}")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and _SHA.fullmatch(value) else None


def _integer(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _binding(value: Mapping[str, Any] | None) -> dict[str, str]:
    value = _mapping(value)
    if any(not isinstance(value.get(key), str) or not value[key] or len(value[key]) > 500 for key in BINDING_FIELDS):
        raise ValueError("scanner_artifact_source_invalid")
    if not re.fullmatch(r"[a-f0-9]{40}", value["commit_sha"]):
        raise ValueError("scanner_artifact_source_invalid")
    return {key: value[key] for key in BINDING_FIELDS}


def binding_from_record(record: Mapping[str, Any]) -> dict[str, str] | None:
    try:
        return _binding(record)
    except ValueError:
        return None


def _artifact_id(binding: Mapping[str, str]) -> str:
    return "scanartifact_" + _sha(json.dumps(dict(binding), sort_keys=True, separators=(",", ":")).encode())


class ImmutableArtifactConflict(ValueError):
    pass


class ScannerArtifactStore:
    """Dedicated SQL boundary; SQLite is only a local persistence test adapter."""

    def __init__(self, connect: Callable, *, dialect: str = "postgres"):
        if dialect not in {"postgres", "sqlite"}:
            raise ValueError("scanner_artifact_dialect_invalid")
        self.connect = connect
        self.dialect = dialect
        self.placeholder = "%s" if dialect == "postgres" else "?"

    def ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.cursor().execute(SCANNER_ARTIFACT_SCHEMA)
            connection.commit()

    def put(self, binding: Mapping[str, str], compressed: bytes, raw_sha256: str) -> str:
        source = _binding(binding)
        artifact_id = _artifact_id(source)
        values = (artifact_id, *source.values(), raw_sha256, _sha(compressed), compressed, datetime.now(UTC).isoformat())
        placeholders = ",".join([self.placeholder] * len(values))
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO scanner_raw_artifacts (artifact_id,run_id,scan_id,customer_id,project_id,repository,commit_sha,scanner_name,raw_sha256,gzip_sha256,gzip_blob,created_at) "
                f"VALUES ({placeholders}) ON CONFLICT DO NOTHING", values,
            )
            cursor.execute(
                f"SELECT raw_sha256,gzip_sha256,gzip_blob FROM scanner_raw_artifacts WHERE artifact_id={self.placeholder}", (artifact_id,),
            )
            row = cursor.fetchone()
            if isinstance(row, Mapping):
                row = (row["raw_sha256"], row["gzip_sha256"], row["gzip_blob"])
            if row is None or (row[0], row[1], bytes(row[2])) != (raw_sha256, _sha(compressed), compressed):
                connection.rollback()
                raise ImmutableArtifactConflict("immutable_artifact_conflict")
            connection.commit()
        return artifact_id

    def get(self, artifact_id: str, *, limit: int) -> dict[str, Any] | None:
        length = "octet_length" if self.dialect == "postgres" else "length"
        columns = ",".join(BINDING_FIELDS)
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT {columns},raw_sha256,gzip_sha256,{length}(gzip_blob) AS compressed_bytes,"
                f"CASE WHEN {length}(gzip_blob)<={self.placeholder} THEN gzip_blob ELSE NULL END AS gzip_blob "
                f"FROM scanner_raw_artifacts WHERE artifact_id={self.placeholder}", (limit, artifact_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if not isinstance(row, Mapping):
            row = dict(zip((*BINDING_FIELDS, "raw_sha256", "gzip_sha256", "compressed_bytes", "gzip_blob"), row))
        return {"binding": {key: row[key] for key in BINDING_FIELDS}, "sha256": row["raw_sha256"], "gzip_sha256": row["gzip_sha256"], "compressed_bytes": row["compressed_bytes"], "compressed": bytes(row["gzip_blob"]) if row["gzip_blob"] is not None else None}


def _default_store() -> ScannerArtifactStore | None:
    # Reuse the already-selected connection. Never resolve another credential,
    # provision a service, or treat MemoryAdapter/SQLite fallback as PostgreSQL.
    from nico.storage import STORE, PostgresAdapter
    adapter = STORE.adapter
    return ScannerArtifactStore(adapter._connect) if isinstance(adapter, PostgresAdapter) else None


@dataclass(frozen=True)
class ArtifactRead:
    metadata: dict[str, Any]
    compressed: bytes | None = None
    raw: bytes | None = None


def read_scanner_artifact(record: Mapping[str, Any], *, binding: Mapping[str, Any] | None = None, raw_root: Path | str | None = None, limit: int | None = None) -> ArtifactRead:
    from nico.scanner_evidence_pipeline_v1 import DEFAULT_RAW_ROOT
    from nico.scanner_tool_runners import MAX_SCANNER_PARSE_BYTES
    limit = MAX_SCANNER_PARSE_BYTES if limit is None else limit
    artifact = _mapping(record.get("raw_artifact"))
    raw_sha, gzip_sha = _digest(artifact.get("sha256")), _digest(artifact.get("gzip_sha256"))
    backend = artifact.get("storage_backend")
    metadata: dict[str, Any] = {"availability": "checksum_unavailable", "storage_backend": "postgres" if backend == "postgres" else "legacy_filesystem", "sha256": raw_sha, "gzip_sha256": gzip_sha, "declared_raw_bytes": _integer(artifact.get("retained_bytes")), "declared_compressed_bytes": _integer(artifact.get("gzip_bytes")), "actual_raw_bytes": None, "actual_compressed_bytes": None, "redaction_declared": artifact.get("redacted") is True}
    def failure(reason: str) -> ArtifactRead:
        metadata["availability"] = reason
        return ArtifactRead(metadata)
    if not raw_sha or not gzip_sha:
        return failure("checksum_unavailable")
    if record.get("raw_artifact_sha256") is not None and _digest(record["raw_artifact_sha256"]) != raw_sha:
        return failure("artifact_reference_mismatch")
    try:
        if backend == "postgres":
            try:
                expected = _binding(binding)
            except ValueError:
                return failure("source_mismatch")
            if artifact.get("artifact_id") != _artifact_id(expected):
                return failure("source_mismatch")
            store = _default_store()
            if store is None:
                return failure("durable_storage_unavailable")
            stored = store.get(artifact["artifact_id"], limit=limit)
            if stored is None:
                return failure("missing")
            if stored["binding"] != expected:
                return failure("source_mismatch")
            if (stored["sha256"], stored["gzip_sha256"]) != (raw_sha, gzip_sha):
                return failure("artifact_reference_mismatch")
            metadata["actual_compressed_bytes"] = stored["compressed_bytes"]
            if stored["compressed"] is None:
                return failure("verification_limit_exceeded")
            compressed = stored["compressed"]
        elif backend is None:
            key = artifact.get("storage_key")
            if not isinstance(key, str) or not key or len(key) > 1500 or Path(key).is_absolute() or ".." in Path(key).parts:
                return failure("storage_reference_invalid")
            root = Path(DEFAULT_RAW_ROOT if raw_root is None else raw_root).resolve()
            path = (root / key).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                return failure("storage_reference_invalid")
            with path.open("rb") as stream:
                compressed = stream.read(limit + 1)
        else:
            return failure("storage_backend_unsupported")
        metadata["observed_compressed_bytes"] = len(compressed)
        if len(compressed) > limit:
            return failure("verification_limit_exceeded")
        metadata["actual_compressed_bytes"] = len(compressed)
        if _sha(compressed) != gzip_sha:
            return failure("compressed_checksum_mismatch")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            raw = stream.read(limit + 1)
        metadata["observed_raw_bytes"] = len(raw)
        if len(raw) > limit:
            return failure("verification_limit_exceeded")
        metadata["actual_raw_bytes"] = len(raw)
        if _sha(raw) != raw_sha:
            return failure("raw_checksum_mismatch")
        if any(metadata[a] is not None and metadata[a] != metadata[b] for a, b in (("declared_raw_bytes", "actual_raw_bytes"), ("declared_compressed_bytes", "actual_compressed_bytes"))):
            return failure("byte_count_mismatch")
        metadata["availability"] = "verified"
        return ArtifactRead(metadata, compressed, raw)
    except FileNotFoundError:
        return failure("missing")
    except (gzip.BadGzipFile, EOFError, zlib.error):
        return failure("invalid_gzip")
    except (OSError, RuntimeError, ValueError):
        return failure("unreadable" if backend is None else "durable_storage_unavailable")
    except Exception:
        return failure("durable_storage_unavailable")


def persist_scanner_result(record: Mapping[str, Any], *, binding: Mapping[str, Any], raw_root: Path | str | None = None) -> dict[str, Any]:
    """Complete durable retention before the worker publishes tool success."""
    output = deepcopy(dict(record))
    if output.get("status") == "not_applicable" and output.get("applicable") is False and output.get("evidence_required") is False and output.get("applicability_evidence") and not output.get("raw_artifact"):
        return output  # Preserve applicability evidence without completion credit.
    reason = "durable_storage_unavailable"
    try:
        source = _binding(binding)
        commits = [output[key] for key in ("commit_sha", "snapshot_commit_sha", "target_commit_sha") if key in output]
        if not commits or any(value != source["commit_sha"] for value in commits) or (output.get("scanner_name") or output.get("tool")) != source["scanner_name"]:
            raise ValueError("scanner_artifact_source_invalid")
        if any(key in output and output[key] != source[key] for key in BINDING_FIELDS):
            raise ValueError("scanner_artifact_source_invalid")
        store = _default_store()
        if store is None:
            raise RuntimeError("durable_storage_unavailable")
        read = read_scanner_artifact(output, binding=source, raw_root=raw_root)
        if read.metadata["availability"] != "verified":
            reason = read.metadata["availability"]
            raise ValueError("scanner_artifact_bytes_unverified")
        artifact_id = store.put(source, read.compressed, read.metadata["sha256"])
        output["raw_artifact"] = {**dict(output["raw_artifact"]), "storage_backend": "postgres", "artifact_id": artifact_id}
        output.update(source)
        output["raw_artifact_retention_complete"] = True
        output["raw_artifact_durability"] = {"version": VERSION, "status": "persisted", "backend": "postgres", "original_compressed_bytes_preserved": True}
        output["artifact_hash"] = _sha(json.dumps({key: value for key, value in output.items() if key != "artifact_hash"}, sort_keys=True, separators=(",", ":"), default=str).encode())
        return output
    except ImmutableArtifactConflict:
        reason = "immutable_artifact_conflict"
    except ValueError as exc:
        if str(exc) == "scanner_artifact_source_invalid":
            reason = "source_mismatch"
    except Exception:
        pass  # Store errors may contain credentials; disclose only a fixed class.
    output["raw_artifact_retention_complete"] = False
    output["raw_artifact_durability"] = {"version": VERSION, "status": "incomplete", "reason": reason}
    for key in ("completed", "verified", "verified_complete", "verified_for_this_report"):
        output[key] = False
    if output.get("status") in {"completed", "complete", "passed", "success"}:
        output["status"] = "failed"
    output["failure_or_unavailable_reason"] = "Durable scanner evidence retention is incomplete."
    return output
