"""Inactive durable implementation of the short-lived OAuth state store.

The caller supplies a fresh non-autocommit connection to trusted storage.
No credentials, session cookies, routes or migration execution live here.
"""
from contextlib import closing, contextmanager
from math import isfinite

from .oauth_state import Pending, TOKEN

_TABLE = "nico_self_serve_oauth_pending"
_SCHEMA = f"""CREATE TABLE {_TABLE} (
    state_hash {{binary_type}} NOT NULL PRIMARY KEY,
    browser_hash {{binary_type}} NOT NULL,
    redirect_uri TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL,
    verifier TEXT NOT NULL
)"""
SQLITE_SCHEMA = _SCHEMA.format(binary_type="BLOB")
POSTGRES_SCHEMA = _SCHEMA.format(binary_type="BYTEA")


def _digest(value):
    return type(value) is bytes and len(value) == 32


def _timestamp(value):
    return type(value) in (int, float) and 0 <= value < 2**53 and isfinite(value)


class SqlOAuthStateStore:
    """Consume commits before returning; a subsequent failed exchange cannot reopen state."""

    def __init__(self, connect, *, dialect):
        if dialect not in ("sqlite", "postgres"):
            raise ValueError("unknown OAuth state storage dialect")
        self._connect = connect
        self._p = "?" if dialect == "sqlite" else "%s"

    @contextmanager
    def _transaction(self):
        with closing(self._connect()) as conn:
            if getattr(conn, "autocommit", False) is True or getattr(conn, "isolation_level", "transactional") is None and self._p == "?":
                raise ValueError("OAuth state requires non-autocommit connection")
            try:
                with closing(conn.cursor()) as cursor:
                    yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def insert_unique(self, state_hash, pending):
        if (
            not _digest(state_hash) or type(pending) is not Pending
            or not _digest(pending.browser_hash) or not _timestamp(pending.expires_at)
            or type(pending.redirect_uri) is not str or not pending.redirect_uri
            or type(pending.verifier) is not str or not TOKEN.fullmatch(pending.verifier)
        ):
            raise ValueError("invalid pending OAuth state")
        holders = ", ".join((self._p,) * 5)
        with self._transaction() as cursor:
            cursor.execute(
                f"INSERT INTO {_TABLE} (state_hash, browser_hash, redirect_uri, expires_at, verifier) "
                f"VALUES ({holders})", (state_hash, pending.browser_hash, pending.redirect_uri,
                                        pending.expires_at, pending.verifier),
            )

    def consume_matching(self, state_hash, browser_hash, redirect_uri, now):
        if (not _digest(state_hash) or not _digest(browser_hash) or
                type(redirect_uri) is not str or not redirect_uri or not _timestamp(now)):
            return None
        p = self._p
        with self._transaction() as cursor:
            cursor.execute(
                f"DELETE FROM {_TABLE} WHERE state_hash = {p} AND browser_hash = {p} "
                f"AND redirect_uri = {p} AND expires_at > {p} RETURNING expires_at, verifier",
                (state_hash, browser_hash, redirect_uri, now),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            expires_at, verifier = row
            if (not _timestamp(expires_at) or type(verifier) is not str or
                    TOKEN.fullmatch(verifier) is None):
                return None
            return Pending(browser_hash, redirect_uri, expires_at, verifier)
