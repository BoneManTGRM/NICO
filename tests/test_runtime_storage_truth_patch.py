from __future__ import annotations

from pathlib import Path

import nico.express_async_api as express
import nico.runtime_storage_truth_patch as truth
import nico.storage as storage
from nico.durable_runtime_storage import SQLiteRuntimeAdapter


def test_writable_sqlite_is_not_called_deployment_durable_without_verified_mount(monkeypatch, tmp_path: Path) -> None:
    truth.install_runtime_storage_truth()
    monkeypatch.delenv("NICO_SQLITE_DURABLE_MOUNT_VERIFIED", raising=False)
    adapter = SQLiteRuntimeAdapter(tmp_path / "runtime.sqlite3")

    status = adapter.status()

    assert status["persistence_available"] is True
    assert status["durability_verified"] is False
    assert status["durable"] is False
    assert "container replacement" in status["durability_warning"]


def test_explicit_verified_sqlite_mount_reports_durability(monkeypatch, tmp_path: Path) -> None:
    truth.install_runtime_storage_truth()
    monkeypatch.setenv("NICO_SQLITE_DURABLE_MOUNT_VERIFIED", "true")
    adapter = SQLiteRuntimeAdapter(tmp_path / "runtime.sqlite3")

    status = adapter.status()

    assert status["persistence_available"] is True
    assert status["durability_verified"] is True
    assert status["durable"] is True


def test_express_persistence_uses_verified_durability_not_writability(monkeypatch, tmp_path: Path) -> None:
    truth.install_runtime_storage_truth()
    monkeypatch.delenv("NICO_SQLITE_DURABLE_MOUNT_VERIFIED", raising=False)
    runtime_store = storage.Storage.__new__(storage.Storage)
    runtime_store.database_url = ""
    runtime_store.disable_postgres = False
    runtime_store.adapter_error = ""
    runtime_store.adapter = SQLiteRuntimeAdapter(tmp_path / "runtime.sqlite3")
    monkeypatch.setattr(storage, "STORE", runtime_store)

    persistence = express._persistence()

    assert persistence["recorded"] is True
    assert persistence["adapter"] == "sqlite"
    assert persistence["durable"] is False
    assert persistence["durability_verified"] is False
    assert "container replacement" in persistence["warning"]


def test_postgres_status_remains_verified_durable_without_exposing_connection_details() -> None:
    truth.install_runtime_storage_truth()

    class FakePostgres:
        def status(self):
            return {
                "mode": "postgres",
                "adapter": "postgres",
                "persistence_available": True,
                "persistence_note": "Postgres persistence is active.",
            }

    wrapped = truth._wrap_status(FakePostgres, lambda _self, result: bool(result.get("persistence_available")))
    assert wrapped is True
    status = FakePostgres().status()
    assert status["durability_verified"] is True
    assert status["durable"] is True
    assert "DATABASE_URL" not in repr(status)
