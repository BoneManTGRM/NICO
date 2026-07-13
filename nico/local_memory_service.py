from __future__ import annotations

from typing import Any, Protocol

from nico.local_reporting_service import analyze_memory
from nico.local_runtime_config import DB_PATH
from nico.local_store import LocalStore


class LocalMemoryStore(Protocol):
    def payloads(self, table: str) -> list[dict[str, Any]]: ...


def memory_summary(
    *,
    store: LocalMemoryStore | None = None,
) -> dict[str, Any]:
    active_store = store if store is not None else LocalStore(DB_PATH)
    memory = active_store.payloads("memory")
    findings = active_store.payloads("findings")
    return {
        "items": memory,
        "analysis": analyze_memory(memory, findings),
    }


__all__ = ["LocalMemoryStore", "memory_summary"]
