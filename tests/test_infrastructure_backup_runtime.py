from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from nico.infrastructure_backup_runtime import (
    BackupRuntimeError,
    PostgresBackupRuntime,
    SQLiteBackupRuntime,
    sqlite_database_fingerprints,
)


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, integrity TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE artifacts (artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, digest TEXT NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO runs VALUES (?, ?, ?)",
        [
            ("run-1", 4, "sha256:one"),
            ("run-2", 7, "sha256:two"),
        ],
    )
    connection.executemany(
        "INSERT INTO artifacts VALUES (?, ?, ?)",
        [
            ("artifact-1", "run-1", "sha256:a"),
            ("artifact-2", "run-2", "sha256:b"),
        ],
    )
    connection.commit()
    connection.close()


def test_sqlite_backup_restore_preserves_selected_table_truth(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backups" / "nico.sqlite3"
    restored = tmp_path / "restore" / "nico.sqlite3"
    _database(source)
    runtime = SQLiteBackupRuntime(encrypted_artifact=True)

    artifact = runtime.backup(
        source_path=source,
        artifact_path=backup,
        exact_sha="a" * 40,
    )
    proof = runtime.restore_and_verify(
        source_path=source,
        artifact=artifact,
        restore_path=restored,
        tables=("runs", "artifacts"),
    )

    assert artifact.adapter == "sqlite"
    assert artifact.artifact_sha256.startswith("sha256:")
    assert artifact.size_bytes > 0
    assert artifact.encrypted is True
    assert proof.equivalent is True
    assert proof.issues == ()
    assert {item.table for item in proof.source_fingerprints} == {"runs", "artifacts"}
    assert proof.source_fingerprints == proof.restored_fingerprints
    assert proof.recovery_time_seconds >= 0


def test_sqlite_restore_detects_artifact_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    _database(source)
    runtime = SQLiteBackupRuntime()
    artifact = runtime.backup(source_path=source, artifact_path=backup, exact_sha="a" * 40)
    backup.write_bytes(b"tampered")

    with pytest.raises(BackupRuntimeError, match="backup_artifact_digest_mismatch"):
        runtime.restore_and_verify(
            source_path=source,
            artifact=artifact,
            restore_path=tmp_path / "restore.sqlite3",
            tables=("runs",),
        )


def test_sqlite_fingerprint_requires_existing_tables_and_bounded_samples(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    _database(source)
    with pytest.raises(BackupRuntimeError, match="backup_table_missing"):
        sqlite_database_fingerprints(source, tables=("missing",))
    with pytest.raises(ValueError, match="backup_sample_limit_invalid"):
        sqlite_database_fingerprints(source, tables=("runs",), sample_limit=0)


class FakeCommandRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str], int]] = []

    def __call__(self, command, *, environment, timeout_seconds):
        command_tuple = tuple(command)
        self.calls.append((command_tuple, dict(environment), timeout_seconds))
        for token in command_tuple:
            if token.startswith("--file="):
                Path(token.split("=", 1)[1]).write_bytes(b"postgres-custom-backup")
        return subprocess.CompletedProcess(command_tuple, 0, "", "")


def test_postgres_backup_restore_uses_named_services_and_no_raw_credentials(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    runtime = PostgresBackupRuntime(
        source_service="nico_source",
        restore_service="nico_restore",
        runner=runner,
        timeout_seconds=120,
    )
    artifact = runtime.backup(
        artifact_path=tmp_path / "nico.dump",
        exact_sha="a" * 40,
        environment={"PGSERVICEFILE": "/run/secrets/pg_service.conf"},
    )
    elapsed = runtime.restore(
        artifact=artifact,
        environment={"PGSERVICEFILE": "/run/secrets/pg_service.conf"},
    )

    assert artifact.adapter == "postgres"
    assert artifact.source_identity == "service:nico_source"
    assert artifact.encrypted is True
    assert artifact.artifact_sha256.startswith("sha256:")
    assert elapsed >= 0
    assert runner.calls[0][0][0] == "pg_dump"
    assert "service=nico_source" in runner.calls[0][0]
    assert runner.calls[1][0][0] == "pg_restore"
    assert "--dbname=service=nico_restore" in runner.calls[1][0]
    rendered = str(runner.calls)
    assert "DATABASE_URL" not in rendered
    assert "PGPASSWORD" not in rendered


def test_postgres_runtime_rejects_same_service_and_raw_credentials(tmp_path: Path) -> None:
    with pytest.raises(BackupRuntimeError, match="restore_service_must_be_isolated"):
        PostgresBackupRuntime(source_service="same", restore_service="same")

    runtime = PostgresBackupRuntime(
        source_service="source",
        restore_service="restore",
        runner=FakeCommandRunner(),
    )
    with pytest.raises(BackupRuntimeError, match="raw_credentials_forbidden"):
        runtime.backup(
            artifact_path=tmp_path / "nico.dump",
            exact_sha="a" * 40,
            environment={"DATABASE_URL": "postgres://secret"},
        )


def test_postgres_restore_rejects_tampered_artifact(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    runtime = PostgresBackupRuntime(
        source_service="source",
        restore_service="restore",
        runner=runner,
    )
    artifact = runtime.backup(
        artifact_path=tmp_path / "nico.dump",
        exact_sha="a" * 40,
    )
    Path(artifact.artifact_path).write_bytes(b"changed")
    with pytest.raises(BackupRuntimeError, match="backup_artifact_digest_mismatch"):
        runtime.restore(artifact=artifact)
