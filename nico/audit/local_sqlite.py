from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nico.cli import DB_PATH
from nico.security.masking import mask_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LocalAuditRecord:
    action: str
    actor: str = "local-operator"
    tenant_id: str = "local"
    detail: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    approval_required: bool = False
    created_at: str = field(default_factory=_now)


class LocalAuditSQLiteStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.db() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    approval_required INTEGER NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def append(self, record: LocalAuditRecord) -> dict:
        safe_detail = {key: mask_text(str(value)) for key, value in record.detail.items()}
        with self.db() as db:
            cursor = db.execute(
                """
                INSERT INTO audit_events(action, actor, tenant_id, risk_level, approval_required, detail, created_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    record.action,
                    record.actor,
                    record.tenant_id,
                    record.risk_level,
                    int(record.approval_required),
                    json.dumps(safe_detail, sort_keys=True),
                    record.created_at,
                ),
            )
            record_id = cursor.lastrowid
        return {"id": record_id, **record.__dict__, "detail": safe_detail}

    def latest(self, limit: int = 25, tenant_id: str = "local") -> list[dict]:
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM audit_events WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["approval_required"] = bool(item["approval_required"])
            item["detail"] = json.loads(item["detail"])
            result.append(item)
        return result
