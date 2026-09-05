"""Backup receipts must describe observed bytes and never expose command secrets."""
from __future__ import annotations

import sqlite3
import subprocess
import traceback
from pathlib import Path

import pytest

from nico.infrastructure_backup_runtime import (
    BackupRuntimeError, PostgresBackupRuntime, SQLiteBackupRuntime,
)

SECRET = "synthetic-backup-secret-never-display"


class DumpRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, command, *, environment, timeout_seconds):
        self.calls.append(tuple(command))
        for token in command:
            if token.startswith("--file="):
                Path(token.split("=", 1)[1]).write_bytes(b"PGDMP\x00unencrypted fixture")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_plain_postgres_dump_is_not_reported_as_encrypted(tmp_path):
    runner = DumpRunner()
    runtime = PostgresBackupRuntime(source_service="source", restore_service="scratch", runner=runner)
    artifact = runtime.backup(artifact_path=tmp_path / "backup.dump", exact_sha="a" * 40)
    assert Path(artifact.artifact_path).read_bytes().startswith(b"PGDMP")
    assert artifact.encrypted is False


@pytest.mark.parametrize("adapter", ["postgres", "sqlite"])
def test_requested_encryption_requires_a_real_encrypting_implementation(adapter):
    with pytest.raises(BackupRuntimeError, match="encryption_not_implemented"):
        if adapter == "postgres":
            PostgresBackupRuntime(source_service="source", restore_service="scratch", encrypted_artifact=True)
        else:
            SQLiteBackupRuntime(encrypted_artifact=True)


@pytest.mark.parametrize("adapter", ["postgres", "sqlite"])
def test_receipt_encryption_cannot_be_manufactured_by_mutating_an_option(tmp_path, adapter):
    if adapter == "postgres":
        runtime = PostgresBackupRuntime(source_service="source", restore_service="scratch", runner=DumpRunner(), encrypted_artifact=False)
        runtime.encrypted_artifact = True
        result = runtime.backup(artifact_path=tmp_path / "backup.dump", exact_sha="a" * 40)
    else:
        source = tmp_path / "source.sqlite3"
        with sqlite3.connect(source) as connection:
            connection.execute("CREATE TABLE runs (id INTEGER)")
        runtime = SQLiteBackupRuntime()
        runtime.encrypted_artifact = True
        result = runtime.backup(source_path=source, artifact_path=tmp_path / "backup.sqlite3", exact_sha="a" * 40)
    assert result.encrypted is False


@pytest.mark.parametrize("failure", ["stderr", "timeout", "oserror", "subprocess"])
def test_backup_errors_never_expose_raw_process_diagnostics(tmp_path, failure):
    def failed(command, *, environment, timeout_seconds):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, timeout_seconds, output=SECRET, stderr=SECRET)
        if failure == "oserror":
            raise OSError(SECRET)
        if failure == "subprocess":
            raise subprocess.CalledProcessError(1, command, output=SECRET, stderr=SECRET)
        return subprocess.CompletedProcess(command, 2, SECRET, "postgres://operator:" + SECRET + "@database")
    runtime = PostgresBackupRuntime(source_service="source", restore_service="scratch", runner=failed)
    try:
        runtime.backup(artifact_path=tmp_path / "backup.dump", exact_sha="a" * 40)
    except Exception as exc:
        assert isinstance(exc, BackupRuntimeError)
        assert SECRET not in str(exc)
        assert SECRET not in "".join(traceback.format_exception(exc))
        assert not (tmp_path / "backup.dump").exists()
    else:
        pytest.fail("failed backup was accepted")
