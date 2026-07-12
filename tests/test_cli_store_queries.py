from __future__ import annotations

from pathlib import Path

import pytest

from nico.cli import Store


def test_rows_uses_supported_static_queries(tmp_path: Path) -> None:
    store = Store(tmp_path / "nico.sqlite3")
    store.save_memory({"id": "memory-1", "value": "ok"})

    rows = store.rows("memory")

    assert rows[0]["id"] == "memory-1"


def test_rows_rejects_unknown_table_name(tmp_path: Path) -> None:
    store = Store(tmp_path / "nico.sqlite3")

    with pytest.raises(ValueError, match="unsupported table"):
        store.rows("memory; DROP TABLE scans")

    # The database remains usable after the rejected request.
    assert store.rows("scans") == []
