from __future__ import annotations

import sys
from types import ModuleType

import nico.comprehensive_runtime as runtime


class _FakeConnection:
    pass


def test_comprehensive_runtime_postgres_factory_uses_canonical_bounds(monkeypatch) -> None:
    monkeypatch.setenv("NICO_POSTGRES_CONNECT_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("NICO_POSTGRES_STATEMENT_TIMEOUT_MS", "12345")

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    connection = _FakeConnection()
    psycopg = ModuleType("psycopg")

    def connect(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return connection

    psycopg.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)

    database_url = "postgresql://nico@example.invalid/nico"
    factory = runtime._postgres_connection_factory(database_url)

    assert factory() is connection
    assert calls == [
        (
            (database_url,),
            {
                "connect_timeout": 7,
                "options": "-c statement_timeout=12345",
            },
        )
    ]


def test_comprehensive_runtime_postgres_factory_preserves_url_validation() -> None:
    for value, expected in (
        ("", "comprehensive_database_url_required"),
        ("sqlite:///tmp/nico.db", "comprehensive_database_url_must_be_postgres"),
    ):
        try:
            runtime._postgres_connection_factory(value)
        except RuntimeError as exc:
            assert str(exc) == expected
        else:  # pragma: no cover - failure message is clearer than pytest.raises here
            raise AssertionError(f"expected RuntimeError for {value!r}")
