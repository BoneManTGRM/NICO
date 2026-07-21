from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


class BackupRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupArtifact:
    adapter: str
    source_identity: str
    artifact_path: str
    artifact_sha256: str
    created_at_epoch: float
    size_bytes: int
    encrypted: bool
    exact_sha: str


@dataclass(frozen=True)
class TableFingerprint:
    table: str
    row_count: int
    schema_sha256: str
    sample_sha256: str
    sampled_rows: int


@dataclass(frozen=True)
class RestoreVerification:
    source_fingerprints: tuple[TableFingerprint, ...]
    restored_fingerprints: tuple[TableFingerprint, ...]
    equivalent: bool
    issues: tuple[str, ...]
    recovery_time_seconds: float


class CommandRunner(Protocol):
    def __call__(
        self,
        command: Sequence[str],
        *,
        environment: Mapping[str, str],
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        ...


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _quote_identifier(value: str) -> str:
    token = str(value or "")
    if not token or "\x00" in token:
        raise BackupRuntimeError("backup_table_identifier_invalid")
    return '"' + token.replace('"', '""') + '"'


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_sha256": sha256(value).hexdigest(), "size": len(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sqlite_table_fingerprint(
    connection: sqlite3.Connection,
    table: str,
    *,
    sample_limit: int = 1000,
) -> TableFingerprint:
    if sample_limit < 1 or sample_limit > 100_000:
        raise ValueError("backup_sample_limit_invalid")
    identifier = _quote_identifier(table)
    schema_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if schema_row is None or not schema_row[0]:
        raise BackupRuntimeError(f"backup_table_missing:{table}")
    schema = str(schema_row[0])
    row_count = int(connection.execute(f"SELECT COUNT(*) FROM {identifier}").fetchone()[0])
    cursor = connection.execute(f"SELECT * FROM {identifier} LIMIT ?", (sample_limit,))
    column_names = [str(item[0]) for item in cursor.description or ()]
    sample_rows = cursor.fetchall()
    canonical = json.dumps(
        {
            "columns": column_names,
            "rows": [
                [_canonical_value(value) for value in row]
                for row in sample_rows
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return TableFingerprint(
        table=table,
        row_count=row_count,
        schema_sha256=f"sha256:{sha256(schema.encode('utf-8')).hexdigest()}",
        sample_sha256=f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}",
        sampled_rows=len(sample_rows),
    )


def sqlite_database_fingerprints(
    path: str | Path,
    *,
    tables: Iterable[str],
    sample_limit: int = 1000,
) -> tuple[TableFingerprint, ...]:
    database = Path(path)
    if not database.exists() or not database.is_file():
        raise BackupRuntimeError("backup_source_database_missing")
    selected = tuple(dict.fromkeys(str(item) for item in tables if str(item)))
    if not selected:
        raise BackupRuntimeError("backup_tables_required")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return tuple(
            sqlite_table_fingerprint(connection, table, sample_limit=sample_limit)
            for table in selected
        )
    finally:
        connection.close()


class SQLiteBackupRuntime:
    def __init__(self, *, encrypted_artifact: bool = False) -> None:
        self.encrypted_artifact = bool(encrypted_artifact)

    def backup(
        self,
        *,
        source_path: str | Path,
        artifact_path: str | Path,
        exact_sha: str,
    ) -> BackupArtifact:
        source = Path(source_path).resolve()
        artifact = Path(artifact_path).resolve()
        if not source.exists() or not source.is_file():
            raise BackupRuntimeError("backup_source_database_missing")
        if source == artifact:
            raise BackupRuntimeError("backup_artifact_must_differ_from_source")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        temporary = artifact.with_suffix(artifact.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        destination_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA quick_check")
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()
        check = sqlite3.connect(temporary)
        try:
            result = check.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]).lower() != "ok":
                raise BackupRuntimeError("backup_sqlite_quick_check_failed")
        finally:
            check.close()
        temporary.replace(artifact)
        return BackupArtifact(
            adapter="sqlite",
            source_identity=str(source),
            artifact_path=str(artifact),
            artifact_sha256=_sha256_file(artifact),
            created_at_epoch=time.time(),
            size_bytes=artifact.stat().st_size,
            encrypted=self.encrypted_artifact,
            exact_sha=str(exact_sha or ""),
        )

    def restore_and_verify(
        self,
        *,
        source_path: str | Path,
        artifact: BackupArtifact,
        restore_path: str | Path,
        tables: Iterable[str],
        sample_limit: int = 1000,
    ) -> RestoreVerification:
        started = time.perf_counter()
        if artifact.adapter != "sqlite":
            raise BackupRuntimeError("backup_adapter_mismatch")
        artifact_path = Path(artifact.artifact_path)
        if not artifact_path.exists() or _sha256_file(artifact_path) != artifact.artifact_sha256:
            raise BackupRuntimeError("backup_artifact_digest_mismatch")
        restore = Path(restore_path).resolve()
        source = Path(source_path).resolve()
        if restore == source or restore == artifact_path.resolve():
            raise BackupRuntimeError("restore_target_must_be_isolated")
        restore.parent.mkdir(parents=True, exist_ok=True)
        temporary = restore.with_suffix(restore.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        shutil.copyfile(artifact_path, temporary)
        check = sqlite3.connect(temporary)
        try:
            result = check.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]).lower() != "ok":
                raise BackupRuntimeError("restore_sqlite_quick_check_failed")
        finally:
            check.close()
        temporary.replace(restore)
        source_fingerprints = sqlite_database_fingerprints(
            source,
            tables=tables,
            sample_limit=sample_limit,
        )
        restored_fingerprints = sqlite_database_fingerprints(
            restore,
            tables=tables,
            sample_limit=sample_limit,
        )
        issues: list[str] = []
        source_by_table = {item.table: item for item in source_fingerprints}
        restored_by_table = {item.table: item for item in restored_fingerprints}
        if set(source_by_table) != set(restored_by_table):
            issues.append("restore_table_set_mismatch")
        for table, source_fingerprint in source_by_table.items():
            restored_fingerprint = restored_by_table.get(table)
            if restored_fingerprint is None:
                continue
            if source_fingerprint.row_count != restored_fingerprint.row_count:
                issues.append(f"restore_row_count_mismatch:{table}")
            if source_fingerprint.schema_sha256 != restored_fingerprint.schema_sha256:
                issues.append(f"restore_schema_mismatch:{table}")
            if source_fingerprint.sample_sha256 != restored_fingerprint.sample_sha256:
                issues.append(f"restore_sample_mismatch:{table}")
        return RestoreVerification(
            source_fingerprints=source_fingerprints,
            restored_fingerprints=restored_fingerprints,
            equivalent=not issues,
            issues=tuple(issues),
            recovery_time_seconds=time.perf_counter() - started,
        )


def default_command_runner(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        env={**os.environ, **dict(environment)},
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


class PostgresBackupRuntime:
    """Runs pg_dump/pg_restore through named libpq services, never raw URLs in argv."""

    def __init__(
        self,
        *,
        source_service: str,
        restore_service: str,
        runner: CommandRunner = default_command_runner,
        timeout_seconds: int = 900,
        encrypted_artifact: bool = True,
    ) -> None:
        self.source_service = self._service(source_service)
        self.restore_service = self._service(restore_service)
        if self.source_service == self.restore_service:
            raise BackupRuntimeError("postgres_restore_service_must_be_isolated")
        self.runner = runner
        self.timeout_seconds = max(30, int(timeout_seconds))
        self.encrypted_artifact = bool(encrypted_artifact)

    @staticmethod
    def _service(value: str) -> str:
        token = str(value or "").strip()
        if not token or not token.replace("_", "").replace("-", "").isalnum():
            raise BackupRuntimeError("postgres_service_name_invalid")
        return token

    @staticmethod
    def _safe_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
        selected = dict(environment or {})
        forbidden = [key for key in selected if key.upper() in {"DATABASE_URL", "PGPASSWORD"}]
        if forbidden:
            raise BackupRuntimeError("postgres_raw_credentials_forbidden")
        return selected

    def _run(self, command: Sequence[str], *, environment: Mapping[str, str]) -> None:
        result = self.runner(
            command,
            environment=environment,
            timeout_seconds=self.timeout_seconds,
        )
        if result.returncode != 0:
            safe_error = " ".join(str(result.stderr or "").split())[:500]
            raise BackupRuntimeError(f"postgres_backup_command_failed:{safe_error or result.returncode}")

    def backup(
        self,
        *,
        artifact_path: str | Path,
        exact_sha: str,
        environment: Mapping[str, str] | None = None,
    ) -> BackupArtifact:
        artifact = Path(artifact_path).resolve()
        artifact.parent.mkdir(parents=True, exist_ok=True)
        temporary = artifact.with_suffix(artifact.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        env = self._safe_environment(environment)
        self._run(
            (
                "pg_dump",
                f"service={self.source_service}",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                f"--file={temporary}",
            ),
            environment=env,
        )
        if not temporary.exists() or temporary.stat().st_size < 1:
            raise BackupRuntimeError("postgres_backup_artifact_missing")
        temporary.replace(artifact)
        return BackupArtifact(
            adapter="postgres",
            source_identity=f"service:{self.source_service}",
            artifact_path=str(artifact),
            artifact_sha256=_sha256_file(artifact),
            created_at_epoch=time.time(),
            size_bytes=artifact.stat().st_size,
            encrypted=self.encrypted_artifact,
            exact_sha=str(exact_sha or ""),
        )

    def restore(
        self,
        *,
        artifact: BackupArtifact,
        environment: Mapping[str, str] | None = None,
        clean: bool = True,
    ) -> float:
        started = time.perf_counter()
        if artifact.adapter != "postgres":
            raise BackupRuntimeError("backup_adapter_mismatch")
        path = Path(artifact.artifact_path)
        if not path.exists() or _sha256_file(path) != artifact.artifact_sha256:
            raise BackupRuntimeError("backup_artifact_digest_mismatch")
        env = self._safe_environment(environment)
        command = [
            "pg_restore",
            f"--dbname=service={self.restore_service}",
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
        ]
        if clean:
            command.extend(("--clean", "--if-exists"))
        command.append(str(path))
        self._run(tuple(command), environment=env)
        return time.perf_counter() - started


__all__ = [
    "BackupArtifact",
    "BackupRuntimeError",
    "CommandRunner",
    "PostgresBackupRuntime",
    "RestoreVerification",
    "SQLiteBackupRuntime",
    "TableFingerprint",
    "default_command_runner",
    "sqlite_database_fingerprints",
    "sqlite_table_fingerprint",
]
