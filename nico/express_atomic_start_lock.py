from __future__ import annotations

import hashlib
from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator

PATCH_VERSION = "nico.express_atomic_start_lock.v1"
_LOCKS_GUARD = Lock()
_MEMORY_LOCKS: dict[int, Lock] = {}


def _scope_lock_id(scope: tuple[str, str, str]) -> int:
    raw = "\x1f".join(scope).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=False)
    return value - (1 << 64) if value >= (1 << 63) else value


def _memory_lock(lock_id: int) -> Lock:
    with _LOCKS_GUARD:
        lock = _MEMORY_LOCKS.get(lock_id)
        if lock is None:
            lock = Lock()
            _MEMORY_LOCKS[lock_id] = lock
        return lock


@contextmanager
def atomic_express_start_lock(store: Any, scope: tuple[str, str, str]) -> Iterator[dict[str, Any]]:
    """Serialize duplicate-check plus run creation for one exact tenant scope.

    Postgres uses a session advisory lock held on one connection across the
    durable scan and queued-record write. Memory fallback uses a process-local
    keyed lock. The caller must perform both the durable lookup and the start
    operation inside this context.
    """

    lock_id = _scope_lock_id(scope)
    adapter = getattr(store, "adapter", None)
    status = store.status() if hasattr(store, "status") else {}
    if str(status.get("adapter") or status.get("mode") or "").lower() == "postgres":
        connect = getattr(adapter, "_connect", None)
        if not callable(connect):
            raise RuntimeError("Postgres Express start locking is unavailable")
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
            try:
                yield {
                    "version": PATCH_VERSION,
                    "mode": "postgres_advisory_lock",
                    "lock_id": lock_id,
                    "cross_worker": True,
                }
            finally:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                conn.commit()
        return

    lock = _memory_lock(lock_id)
    with lock:
        yield {
            "version": PATCH_VERSION,
            "mode": "process_local_memory_lock",
            "lock_id": lock_id,
            "cross_worker": False,
        }


__all__ = ["PATCH_VERSION", "_scope_lock_id", "atomic_express_start_lock"]
