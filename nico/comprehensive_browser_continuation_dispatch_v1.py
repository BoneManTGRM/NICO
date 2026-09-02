from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

VERSION = "nico.comprehensive_browser_continuation_dispatch.v1"

_ACTIVE_RUNS: set[str] = set()
_ACTIVE_RUNS_LOCK = threading.RLock()


def _advisory_lock_key(run_id: str) -> int:
    raw = int.from_bytes(
        hashlib.sha256(f"{VERSION}:{run_id}".encode("utf-8")).digest()[:8],
        byteorder="big",
        signed=False,
    )
    return raw if raw < 2**63 else raw - 2**64


def _service_store(controller: Any) -> Any:
    service = getattr(controller, "_service", None)
    return getattr(service, "_store", None)


@contextmanager
def _distributed_run_lock(controller: Any, run_id: str) -> Iterator[bool]:
    """Prevent the same run from publishing concurrently across Postgres workers."""

    store = _service_store(controller)
    if getattr(store, "_dialect", "") != "postgres":
        yield True
        return

    connection_factory = getattr(store, "_connection_factory", None)
    if not callable(connection_factory):
        yield False
        return

    key = _advisory_lock_key(run_id)
    connection = None
    try:
        connection = connection_factory()
        cursor = connection.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        row = cursor.fetchone()
        acquired = bool(row and row[0] is True)
    except Exception:
        # The exact run remains unchanged. A later browser tick may retry after the
        # storage connection is healthy; never fall back to an unlocked publication.
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        yield False
        return

    try:
        yield acquired
    finally:
        if acquired:
            try:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (key,))
            except Exception:
                pass
        try:
            connection.close()
        except Exception:
            pass


def dispatch_browser_continuation(
    controller: Any,
    *,
    run_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Launch one exact-run continuation without owning the browser request lifetime.

    Process-local exclusion prevents repeated clicks from multiplying work in one
    worker. A Postgres advisory lock extends that exclusion across workers and is
    released automatically on process or connection loss. The canonical run's existing
    optimistic revision check remains the final write authority.
    """

    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        raise ValueError("run_id_required")

    with _ACTIVE_RUNS_LOCK:
        if normalized_run_id in _ACTIVE_RUNS:
            return {
                "artifact_schema": VERSION,
                "status": "already_active",
                "run_id": normalized_run_id,
                "request_thread_owns_publication": False,
                "duplicate_execution_prevented": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        _ACTIVE_RUNS.add(normalized_run_id)

    body = dict(payload)

    def invoke() -> None:
        try:
            with _distributed_run_lock(controller, normalized_run_id) as acquired:
                if not acquired:
                    return
                controller.continue_run(
                    normalized_run_id,
                    body,
                    browser_projection=True,
                )
        except BaseException:
            # The next exact-run projection remains the public failure/recovery source.
            # Background exception details must not cross the client boundary.
            pass
        finally:
            with _ACTIVE_RUNS_LOCK:
                _ACTIVE_RUNS.discard(normalized_run_id)

    threading.Thread(
        target=invoke,
        name=f"nico-browser-continuation-{normalized_run_id[-12:]}",
        daemon=True,
    ).start()
    return {
        "artifact_schema": VERSION,
        "status": "dispatched",
        "run_id": normalized_run_id,
        "request_thread_owns_publication": False,
        "distributed_lock_required": getattr(
            _service_store(controller), "_dialect", ""
        )
        == "postgres",
        "duplicate_execution_prevented": True,
        "exact_run_recovery_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def active_browser_continuations_for_tests() -> set[str]:
    with _ACTIVE_RUNS_LOCK:
        return set(_ACTIVE_RUNS)


def reset_browser_continuation_dispatch_for_tests() -> None:
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUNS.clear()


__all__ = [
    "VERSION",
    "active_browser_continuations_for_tests",
    "dispatch_browser_continuation",
    "reset_browser_continuation_dispatch_for_tests",
]
