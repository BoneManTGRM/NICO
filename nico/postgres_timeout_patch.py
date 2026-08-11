from __future__ import annotations

import os
from typing import Any

POSTGRES_TIMEOUT_PATCH_VERSION = "nico.postgres_timeout_patch.v1"
_PATCH_MARKER = "_nico_postgres_timeout_patch_v1"


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def postgres_connect_kwargs() -> dict[str, int | str]:
    """Return the canonical bounded connection policy for every Postgres connect."""
    connect_timeout = _bounded_int("NICO_POSTGRES_CONNECT_TIMEOUT_SECONDS", 5, 2, 30)
    statement_timeout_ms = _bounded_int("NICO_POSTGRES_STATEMENT_TIMEOUT_MS", 30000, 5000, 120000)
    return {
        "connect_timeout": connect_timeout,
        "options": f"-c statement_timeout={statement_timeout_ms}",
    }


def install_postgres_timeout_patch() -> dict[str, Any]:
    # Import lazily so nico.storage can consume postgres_connect_kwargs() while its
    # module-level STORE is being initialized. The first schema connection must use
    # the same bounded policy even before this compatibility patch is installed.
    from nico.storage import PostgresAdapter

    current = PostgresAdapter._connect
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": POSTGRES_TIMEOUT_PATCH_VERSION}

    connect_kwargs = postgres_connect_kwargs()

    def bounded_connect(self: PostgresAdapter):
        return self._psycopg.connect(
            self.database_url,
            row_factory=self._dict_row,
            **connect_kwargs,
        )

    setattr(bounded_connect, _PATCH_MARKER, True)
    setattr(bounded_connect, "_nico_previous", current)
    PostgresAdapter._connect = bounded_connect
    return {
        "status": "installed",
        "version": POSTGRES_TIMEOUT_PATCH_VERSION,
        "connect_timeout_seconds": connect_kwargs["connect_timeout"],
        "statement_timeout_ms": int(str(connect_kwargs["options"]).split("=")[-1]),
    }


__all__ = [
    "POSTGRES_TIMEOUT_PATCH_VERSION",
    "install_postgres_timeout_patch",
    "postgres_connect_kwargs",
]
