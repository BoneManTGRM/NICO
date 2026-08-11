from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from functools import wraps
from typing import Any, Iterator

from fastapi import HTTPException

VERSION = "nico.comprehensive_storage_availability_patch.v1"
_CONNECTION_MARKER = "_nico_comprehensive_storage_availability_v1"
_TRANSLATOR_MARKER = "_nico_comprehensive_storage_error_translation_v1"
_PROBE_MARKER = "_nico_comprehensive_live_persistence_probe_v1"


class ComprehensiveStorageUnavailable(RuntimeError):
    """Bounded internal signal that the canonical Comprehensive store is unavailable."""


def _is_storage_exception(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    if isinstance(exc, ComprehensiveStorageUnavailable):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError, sqlite3.OperationalError)):
        return True
    module = type(exc).__module__.lower()
    if module.startswith("psycopg"):
        try:
            import psycopg

            return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
        except Exception:
            return type(exc).__name__ in {
                "OperationalError",
                "InterfaceError",
                "ConnectionTimeout",
            }
    return False


def _storage_http_exception() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "comprehensive_database_unavailable",
            "reason": "comprehensive_database_unavailable",
            "message": (
                "Comprehensive is temporarily unavailable because its durable "
                "production database cannot be reached."
            ),
            "retryable": True,
            "persistence_diagnostic_required": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
    )


def _install_store_guard() -> dict[str, Any]:
    from nico.comprehensive_run_store import ComprehensiveRunStore

    current = ComprehensiveRunStore._connection
    if getattr(current, _CONNECTION_MARKER, False):
        return {
            "status": "already_installed",
            "connection_guard_bound": True,
            "live_probe_bound": callable(
                getattr(ComprehensiveRunStore, "live_persistence_probe", None)
            ),
        }

    @contextmanager
    @wraps(current)
    def guarded_connection(self: ComprehensiveRunStore) -> Iterator[Any]:
        try:
            with current(self) as connection:
                yield connection
        except ComprehensiveStorageUnavailable:
            raise
        except Exception as exc:
            if _is_storage_exception(exc):
                raise ComprehensiveStorageUnavailable(
                    "comprehensive_database_unavailable"
                ) from exc
            raise

    setattr(guarded_connection, _CONNECTION_MARKER, True)
    setattr(guarded_connection, "_nico_previous", current)
    ComprehensiveRunStore._connection = guarded_connection

    def live_persistence_probe(self: ComprehensiveRunStore) -> dict[str, Any]:
        available = False
        try:
            with self._connection() as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT 1")
                available = cursor.fetchone() is not None
        except Exception:
            available = False
        return {
            "artifact_schema": VERSION,
            "status": "ready" if available else "unavailable",
            "available": available,
            "adapter": str(getattr(self, "_dialect", "unknown") or "unknown"),
            "error_detail_exposed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    setattr(live_persistence_probe, _PROBE_MARKER, True)
    ComprehensiveRunStore.live_persistence_probe = live_persistence_probe  # type: ignore[attr-defined]
    return {
        "status": "installed",
        "connection_guard_bound": ComprehensiveRunStore._connection is guarded_connection,
        "live_probe_bound": bool(
            getattr(
                getattr(ComprehensiveRunStore, "live_persistence_probe", None),
                _PROBE_MARKER,
                False,
            )
        ),
    }


def _install_api_translation() -> dict[str, Any]:
    from nico import comprehensive_api_routes as routes
    from nico.comprehensive_run_store import ComprehensiveRunConflict

    routes._SAFE_RUNTIME_REASONS["comprehensive_database_unavailable"] = (
        "Comprehensive is temporarily unavailable because its durable production "
        "database cannot be reached."
    )
    current = routes._translate_error
    if getattr(current, _TRANSLATOR_MARKER, False):
        return {"status": "already_installed", "api_translation_bound": True}

    @wraps(current)
    def translate(exc: Exception) -> HTTPException:
        conflict_cause = exc.__cause__ if isinstance(exc, ComprehensiveRunConflict) else None
        if isinstance(exc, ComprehensiveStorageUnavailable) or _is_storage_exception(conflict_cause):
            return _storage_http_exception()
        return current(exc)

    setattr(translate, _TRANSLATOR_MARKER, True)
    setattr(translate, "_nico_previous", current)
    routes._translate_error = translate
    return {
        "status": "installed",
        "api_translation_bound": routes._translate_error is translate,
    }


def install_comprehensive_storage_availability_patch_v1() -> dict[str, Any]:
    store = _install_store_guard()
    api = _install_api_translation()
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "store": store,
        "api": api,
        "startup_database_failure_becomes_blocked_runtime": True,
        "runtime_database_failure_returns_503": True,
        "automatic_cross_store_fallback": False,
        "canonical_store_identity_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "ComprehensiveStorageUnavailable",
    "VERSION",
    "install_comprehensive_storage_availability_patch_v1",
]
