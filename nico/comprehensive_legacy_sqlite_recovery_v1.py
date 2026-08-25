from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nico.comprehensive_run_store import (
    ComprehensiveRunConflict,
    ComprehensiveRunNotFound,
    ComprehensiveRunStore,
)


VERSION = "nico.comprehensive_legacy_sqlite_recovery.v1"


def _status(
    *,
    source_present: bool,
    source_table_present: bool = False,
    scanned: int = 0,
    imported: int = 0,
    already_present: int = 0,
    invalid: int = 0,
    conflicts: int = 0,
) -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "status": "complete" if source_present else "not_present",
        "source_present": source_present,
        "source_table_present": source_table_present,
        "scanned": scanned,
        "imported": imported,
        "already_present": already_present,
        "invalid": invalid,
        "conflicts": conflicts,
        "source_mutated": False,
        "target_existing_rows_overwritten": False,
        "assessment_rerun": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _readonly_connection(path: Path) -> sqlite3.Connection:
    resolved = str(path.resolve())
    uri = "file:" + quote(resolved, safe="/:") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def recover_legacy_sqlite_runs(
    target_store: ComprehensiveRunStore,
    source_path: str | Path,
) -> dict[str, Any]:
    """Copy valid missing canonical runs from a surviving legacy SQLite store.

    This is a one-way, idempotent startup import into the already-selected canonical
    Postgres store. The SQLite source is opened read-only. Existing target rows always
    win, payloads are accepted only through the canonical run-store validator, and no
    assessment/report/review/approval state is recomputed or weakened.
    """

    path = Path(source_path).expanduser()
    if not path.exists() or not path.is_file():
        return _status(source_present=False)

    scanned = imported = already_present = invalid = conflicts = 0
    try:
        connection = _readonly_connection(path)
    except Exception:
        result = _status(source_present=True, invalid=1)
        result["status"] = "unreadable"
        return result

    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nico_comprehensive_runs'"
        ).fetchone()
        if table is None:
            return _status(source_present=True, source_table_present=False)

        cursor = connection.execute(
            "SELECT run_id, payload FROM nico_comprehensive_runs ORDER BY updated_at ASC, run_id ASC"
        )
        for row in cursor:
            scanned += 1
            run_id = str(row["run_id"] or "").strip()
            raw_payload = row["payload"]
            try:
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
                if not run_id or not isinstance(payload, dict):
                    raise ValueError("legacy_comprehensive_payload_invalid")
                identity = payload.get("identity")
                if not isinstance(identity, dict) or str(identity.get("run_id") or "").strip() != run_id:
                    raise ValueError("legacy_comprehensive_run_identity_mismatch")
            except Exception:
                invalid += 1
                continue

            try:
                target_store.load(run_id)
            except ComprehensiveRunNotFound:
                pass
            except Exception:
                # A target row that exists but cannot currently be loaded must never be
                # replaced by a legacy record without explicit operator intervention.
                conflicts += 1
                continue
            else:
                already_present += 1
                continue

            try:
                target_store.create(payload)
            except ComprehensiveRunConflict:
                # Multiple production workers may race during startup. If another worker
                # imported the same exact run first, treat that as an idempotent success.
                try:
                    target_store.load(run_id)
                except Exception:
                    conflicts += 1
                else:
                    already_present += 1
            except Exception:
                invalid += 1
            else:
                imported += 1
    finally:
        connection.close()

    return _status(
        source_present=True,
        source_table_present=True,
        scanned=scanned,
        imported=imported,
        already_present=already_present,
        invalid=invalid,
        conflicts=conflicts,
    )


__all__ = ["VERSION", "recover_legacy_sqlite_runs"]
