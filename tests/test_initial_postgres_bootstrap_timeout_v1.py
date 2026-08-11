from __future__ import annotations

from nico.postgres_timeout_patch import postgres_connect_kwargs
from nico.storage import PostgresAdapter


class _FakePsycopg:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.connection = object()

    def connect(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self.connection


def test_initial_postgres_connect_is_bounded_before_runtime_patch(monkeypatch) -> None:
    monkeypatch.setenv("NICO_POSTGRES_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("NICO_POSTGRES_STATEMENT_TIMEOUT_MS", "12345")

    fake = _FakePsycopg()
    adapter = object.__new__(PostgresAdapter)
    adapter.database_url = "postgresql://nico@example.invalid/nico"
    adapter._psycopg = fake
    adapter._dict_row = object()

    connection = adapter._connect()

    assert connection is fake.connection
    assert len(fake.calls) == 1
    args, kwargs = fake.calls[0]
    assert args == (adapter.database_url,)
    assert kwargs["row_factory"] is adapter._dict_row
    assert kwargs["connect_timeout"] == 7
    assert kwargs["options"] == "-c statement_timeout=12345"


def test_postgres_connect_policy_preserves_existing_bounds(monkeypatch) -> None:
    monkeypatch.setenv("NICO_POSTGRES_CONNECT_TIMEOUT_SECONDS", "999")
    monkeypatch.setenv("NICO_POSTGRES_STATEMENT_TIMEOUT_MS", "1")

    assert postgres_connect_kwargs() == {
        "connect_timeout": 30,
        "options": "-c statement_timeout=5000",
    }

    monkeypatch.setenv("NICO_POSTGRES_CONNECT_TIMEOUT_SECONDS", "invalid")
    monkeypatch.setenv("NICO_POSTGRES_STATEMENT_TIMEOUT_MS", "invalid")

    assert postgres_connect_kwargs() == {
        "connect_timeout": 5,
        "options": "-c statement_timeout=30000",
    }
