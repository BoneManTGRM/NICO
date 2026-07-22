from __future__ import annotations

from pathlib import Path

from nico.durable_runtime_storage import _path, _resolved_postgres_url


POSTGRES_KEYS = (
    "DATABASE_URL",
    "DATABASE_PRIVATE_URL",
    "POSTGRES_URL",
    "POSTGRES_PRIVATE_URL",
    "RAILWAY_DATABASE_URL",
    "RAILWAY_POSTGRES_URL",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
    "PGSSLMODE",
)


def _clear_postgres(monkeypatch) -> None:
    for key in POSTGRES_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_private_postgres_alias_is_resolved_and_normalized(monkeypatch) -> None:
    _clear_postgres(monkeypatch)
    monkeypatch.setenv("DATABASE_PRIVATE_URL", "postgres://nico:secret@postgres.railway.internal:5432/railway")

    url, source = _resolved_postgres_url()

    assert source == "DATABASE_PRIVATE_URL"
    assert url == "postgresql://nico:secret@postgres.railway.internal:5432/railway"


def test_standard_pg_environment_builds_a_safe_connection_url(monkeypatch) -> None:
    _clear_postgres(monkeypatch)
    monkeypatch.setenv("PGHOST", "postgres.railway.internal")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "nico user")
    monkeypatch.setenv("PGPASSWORD", "p@ss word")
    monkeypatch.setenv("PGDATABASE", "nico/db")
    monkeypatch.setenv("PGSSLMODE", "require")

    url, source = _resolved_postgres_url()

    assert source == "PG*"
    assert "nico%20user:p%40ss%20word" in url
    assert "postgres.railway.internal:5432/nico%2Fdb" in url
    assert url.endswith("?sslmode=require")


def test_railway_volume_path_replaces_only_the_container_default(monkeypatch) -> None:
    monkeypatch.setenv("NICO_SQLITE_PATH", "/data/nico-runtime.sqlite3")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/var/lib/nico-volume")

    assert _path() == Path("/var/lib/nico-volume/nico-runtime.sqlite3")


def test_explicit_operator_sqlite_path_wins_over_railway_volume_hint(monkeypatch) -> None:
    monkeypatch.setenv("NICO_SQLITE_PATH", "/custom/nico.sqlite3")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/var/lib/nico-volume")

    assert _path() == Path("/custom/nico.sqlite3")
