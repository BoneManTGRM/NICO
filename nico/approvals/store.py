from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nico.cli import DB_PATH
from nico.security.masking import mask_secret_value, mask_text

SENSITIVE_DETAIL_KEYS = ("api", "key", "secret", "token", "password", "jwt", "private")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_detail(detail: dict[str, Any]) -> dict[str, str]:
    safe = {}
    for key, value in detail.items():
        text = str(value)
        if any(marker in key.lower() for marker in SENSITIVE_DETAIL_KEYS):
            safe[key] = mask_secret_value(text)
        else:
            safe[key] = mask_text(text)
    return safe


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    action: str
    actor: str = "local-operator"
    tenant_id: str = "local"
    reason: str = "local demo approval gate"
    detail: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class ApprovalDecision:
    request_id: str
    decision: str
    decided_by: str = "local-operator"
    note: str = "local demo decision"
    decided_at: str = field(default_factory=_now)


class LocalApprovalSQLiteStore:
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
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_requests(
                    request_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_decisions(
                    request_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    decided_by TEXT NOT NULL,
                    note TEXT NOT NULL,
                    decided_at TEXT NOT NULL
                );
                """
            )

    def create_request(self, request: ApprovalRequest) -> dict:
        safe_detail = _safe_detail(request.detail)
        with self.db() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO approval_requests(request_id, action, actor, tenant_id, reason, detail, status, created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    request.request_id,
                    request.action,
                    request.actor,
                    request.tenant_id,
                    request.reason,
                    json.dumps(safe_detail, sort_keys=True),
                    request.status,
                    request.created_at,
                ),
            )
        return {**request.__dict__, "detail": safe_detail}

    def pending(self, tenant_id: str = "local") -> list[dict]:
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM approval_requests WHERE tenant_id=? AND status='pending' ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item["detail"])
            result.append(item)
        return result

    def decide(self, decision: ApprovalDecision) -> dict:
        if decision.decision not in {"approved", "denied"}:
            raise ValueError("decision must be approved or denied")
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO approval_decisions(request_id, decision, decided_by, note, decided_at) VALUES(?,?,?,?,?)",
                (decision.request_id, decision.decision, decision.decided_by, mask_text(decision.note), decision.decided_at),
            )
            db.execute(
                "UPDATE approval_requests SET status=? WHERE request_id=?",
                (decision.decision, decision.request_id),
            )
        return decision.__dict__
