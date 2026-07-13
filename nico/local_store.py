from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_POLICY = {
    "autonomy_level": 1,
    "kill_switch": False,
    "allowed_actions": ["scan", "report", "score", "repair_plan", "verify", "memory_update", "create_draft_pr"],
    "approval_required": [
        "production_key_rotation",
        "permanent_account_disable",
        "data_delete",
        "infrastructure_delete",
        "major_dependency_upgrade",
        "dns_change",
        "broad_firewall_change",
        "production_deploy",
        "architecture_rewrite",
    ],
    "blocked_actions": [
        "exploit",
        "credential_theft",
        "phishing",
        "malware",
        "evasion",
        "persistence",
        "unauthorized_scan",
        "destructive_action",
        "auth_bypass",
    ],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalStore:
    """SQLite persistence contract extracted from the legacy CLI.

    This module intentionally preserves the existing schema and method behavior.
    The legacy CLI remains the canonical caller until a later routing PR switches
    imports after compatibility coverage is green.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, kind TEXT, created_at TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, scan_id TEXT, severity TEXT, category TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS drift_events(id TEXT PRIMARY KEY, scan_id TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS repairs(id TEXT PRIMARY KEY, finding_id TEXT, status TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, payload TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, format TEXT, path TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);
                CREATE TABLE IF NOT EXISTS baseline(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS verification(id TEXT PRIMARY KEY, repair_id TEXT, payload TEXT, created_at TEXT);
                """
            )

    def audit(self, action: str, detail: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute(
                "INSERT INTO audit_log(action,detail,created_at) VALUES(?,?,?)",
                (action, json.dumps(detail, sort_keys=True), now()),
            )

    def save_scan(self, scan: dict[str, Any], kind: str) -> None:
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO scans VALUES(?,?,?,?)",
                (scan["id"], kind, scan["created_at"], json.dumps(scan, sort_keys=True)),
            )
            for finding in scan["findings"]:
                db.execute(
                    "INSERT OR REPLACE INTO findings VALUES(?,?,?,?,?)",
                    (
                        finding["id"],
                        scan["id"],
                        finding["severity"],
                        finding["category"],
                        json.dumps(finding, sort_keys=True),
                    ),
                )

    def save_drift(self, scan_id: str, drift: list[dict[str, Any]]) -> None:
        with self.db() as db:
            for event in drift:
                db.execute(
                    "INSERT OR REPLACE INTO drift_events VALUES(?,?,?)",
                    (event["id"], scan_id, json.dumps(event, sort_keys=True)),
                )

    def save_repairs(self, repairs: list[dict[str, Any]]) -> None:
        with self.db() as db:
            for repair in repairs:
                db.execute(
                    "INSERT OR REPLACE INTO repairs VALUES(?,?,?,?)",
                    (
                        repair["id"],
                        repair["finding_id"],
                        repair.get("status", "suggested"),
                        json.dumps(repair, sort_keys=True),
                    ),
                )

    def update_repair_status(self, repair_id: str, status: str) -> dict[str, Any] | None:
        target = None
        for repair in self.payloads("repairs"):
            if repair.get("id") == repair_id or repair.get("repair_id") == repair_id:
                repair["status"] = status
                target = repair
                break
        if target:
            with self.db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO repairs VALUES(?,?,?,?)",
                    (target["id"], target["finding_id"], status, json.dumps(target, sort_keys=True)),
                )
        return target

    def save_memory(self, payload: dict[str, Any]) -> None:
        payload.setdefault("created_at", now())
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO memory VALUES(?,?,?)",
                (payload["id"], json.dumps(payload, sort_keys=True), payload["created_at"]),
            )

    def save_verification(self, result: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO verification VALUES(?,?,?,?)",
                (result["id"], result.get("repair_id"), json.dumps(result, sort_keys=True), result["created_at"]),
            )

    def save_report(self, report_id: str, fmt: str, path: str) -> None:
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO reports VALUES(?,?,?,?)",
                (report_id, fmt, path, now()),
            )

    def rows(self, table: str) -> list[dict[str, Any]]:
        queries = {
            "scans": "SELECT * FROM scans ORDER BY rowid DESC",
            "findings": "SELECT * FROM findings ORDER BY rowid DESC",
            "drift_events": "SELECT * FROM drift_events ORDER BY rowid DESC",
            "repairs": "SELECT * FROM repairs ORDER BY rowid DESC",
            "memory": "SELECT * FROM memory ORDER BY rowid DESC",
            "reports": "SELECT * FROM reports ORDER BY rowid DESC",
            "audit_log": "SELECT * FROM audit_log ORDER BY rowid DESC",
            "verification": "SELECT * FROM verification ORDER BY rowid DESC",
        }
        query = queries.get(table)
        if query is None:
            raise ValueError(f"unsupported table: {table}")
        with self.db() as db:
            rows = db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def payloads(self, table: str) -> list[dict[str, Any]]:
        return [json.loads(row["payload"]) for row in self.rows(table) if row.get("payload")]

    def latest_scan(self) -> dict[str, Any]:
        with self.db() as db:
            row = db.execute("SELECT * FROM scans ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            return {}
        data = dict(row)
        data["payload"] = json.loads(data["payload"])
        data.update(data["payload"])
        return data

    def latest_verification(self) -> dict[str, Any]:
        with self.db() as db:
            row = db.execute("SELECT payload FROM verification ORDER BY created_at DESC LIMIT 1").fetchone()
        return json.loads(row["payload"]) if row else {}

    def baseline(self) -> dict[str, Any] | None:
        with self.db() as db:
            row = db.execute("SELECT payload FROM baseline WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else None

    def save_baseline(self, baseline: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO baseline VALUES(1,?,?)",
                (json.dumps(baseline, sort_keys=True), now()),
            )

    def policy(self) -> dict[str, Any]:
        with self.db() as db:
            row = db.execute("SELECT payload FROM policy WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else DEFAULT_POLICY.copy()

    def save_policy(self, policy: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO policy VALUES(1,?)",
                (json.dumps(policy, sort_keys=True),),
            )
