from __future__ import annotations

from pathlib import Path

import pytest

from nico.cli import Store as LegacyStore
from nico.local_store import DEFAULT_POLICY, LocalStore


@pytest.mark.parametrize("store_type", [LegacyStore, LocalStore])
def test_local_store_round_trip_contract(store_type, tmp_path: Path) -> None:
    store = store_type(tmp_path / f"{store_type.__name__}.sqlite3")
    finding = {
        "id": "finding_1",
        "severity": "high",
        "category": "dependency_risk",
        "title": "Synthetic dependency finding",
    }
    scan = {
        "id": "scan_1",
        "created_at": "2026-07-13T00:00:00+00:00",
        "findings": [finding],
        "files_scanned": ["requirements.txt"],
    }
    repair = {
        "id": "repair_1",
        "finding_id": "finding_1",
        "status": "suggested",
    }
    verification = {
        "id": "verification_1",
        "repair_id": "repair_1",
        "created_at": "2026-07-13T00:01:00+00:00",
        "status": "passed",
    }

    store.save_scan(scan, "repository")
    store.save_drift("scan_1", [{"id": "drift_1", "type": "risk_score_drift"}])
    store.save_repairs([repair])
    store.save_memory({"id": "memory_1", "category": "dependency_risk"})
    store.save_verification(verification)
    store.save_report("report_1", "json", "/tmp/report.json")
    store.save_baseline({"scan_id": "scan_1", "risk_score": 35})
    store.save_policy({**DEFAULT_POLICY, "autonomy_level": 2})
    store.audit("contract_test", {"scan_id": "scan_1"})

    assert store.latest_scan()["id"] == "scan_1"
    assert store.latest_verification()["id"] == "verification_1"
    assert store.baseline() == {"scan_id": "scan_1", "risk_score": 35}
    assert store.policy()["autonomy_level"] == 2
    assert store.payloads("findings")[0]["id"] == "finding_1"
    assert store.payloads("repairs")[0]["id"] == "repair_1"
    assert store.payloads("memory")[0]["id"] == "memory_1"
    assert store.rows("reports")[0]["id"] == "report_1"
    assert store.rows("audit_log")[0]["action"] == "contract_test"

    updated = store.update_repair_status("repair_1", "verified")
    assert updated is not None
    assert updated["status"] == "verified"
    assert store.payloads("repairs")[0]["status"] == "verified"


def test_extracted_store_schema_matches_legacy_store(tmp_path: Path) -> None:
    legacy = LegacyStore(tmp_path / "legacy.sqlite3")
    extracted = LocalStore(tmp_path / "extracted.sqlite3")

    def schema(store) -> list[tuple[str, str]]:
        with store.db() as db:
            rows = db.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [(row["name"], row["sql"]) for row in rows]

    assert schema(extracted) == schema(legacy)


def test_extracted_store_denies_unknown_tables(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store.sqlite3")

    with pytest.raises(ValueError, match="unsupported table"):
        store.rows("unknown")
