from __future__ import annotations

import os
from typing import Any

from nico.storage import PostgresAdapter

POSTGRES_TIMEOUT_PATCH_VERSION = "nico.postgres_timeout_patch.v1"
_PATCH_MARKER = "_nico_postgres_timeout_patch_v1"


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def install_postgres_timeout_patch() -> dict[str, Any]:
    current = PostgresAdapter._connect
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": POSTGRES_TIMEOUT_PATCH_VERSION}

    connect_timeout = _bounded_int("NICO_POSTGRES_CONNECT_TIMEOUT_SECONDS", 5, 2, 30)
    statement_timeout_ms = _bounded_int("NICO_POSTGRES_STATEMENT_TIMEOUT_MS", 30000, 5000, 120000)

    def bounded_connect(self: PostgresAdapter):
        return self._psycopg.connect(
            self.database_url,
            row_factory=self._dict_row,
            connect_timeout=connect_timeout,
            options=f"-c statement_timeout={statement_timeout_ms}",
        )

    setattr(bounded_connect, _PATCH_MARKER, True)
    setattr(bounded_connect, "_nico_previous", current)
    PostgresAdapter._connect = bounded_connect
    return {
        "status": "installed",
        "version": POSTGRES_TIMEOUT_PATCH_VERSION,
        "connect_timeout_seconds": connect_timeout,
        "statement_timeout_ms": statement_timeout_ms,
    }


__all__ = ["POSTGRES_TIMEOUT_PATCH_VERSION", "install_postgres_timeout_patch"]
