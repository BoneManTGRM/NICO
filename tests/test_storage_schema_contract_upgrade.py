"""Upgrade the actual schema validator from the retained pre-scanner contract.

The legacy version/hash come from dfb95519^, before #1519 added
scanner_raw_artifacts. Fixtures are isolated; no production database is used.
"""
from copy import deepcopy

import nico.storage_schema_readiness as readiness
from test_storage_schema_readiness import _FakePostgresAdapter, _FakeStore


LEGACY_VERSION = "2026.07.13.1"
LEGACY_HASH = "8c2ab93e4ad70bc2d1536232d686eda33219d7fbafcd8b0a0e1fb898e0cee274"
LEGACY_ROW = {
    "version": LEGACY_VERSION,
    "contract_sha256": LEGACY_HASH,
    "applied_at": "2026-07-13T00:00:00Z",
    "verified_at": "2026-09-07T00:00:00Z",
}


def test_expanded_contract_uses_new_version_and_preserves_legacy_ledger(monkeypatch):
    contract = readiness.storage_schema_contract()
    legacy_contract = {
        "version": LEGACY_VERSION,
        "tables": {key: value for key, value in contract["tables"].items()
                   if key != "scanner_raw_artifacts"},
        "migration_table": contract["migration_table"],
    }
    assert len(legacy_contract["tables"]) == 13
    assert readiness._canonical_hash(legacy_contract) == LEGACY_HASH
    assert len(contract["tables"]) == 14

    adapter = _FakePostgresAdapter()
    adapter.ledger.append(deepcopy(LEGACY_ROW))
    monkeypatch.setattr(readiness, "_now", lambda: "2026-09-08T21:00:00Z")
    result = readiness.verify_storage_schema(_FakeStore(adapter))

    assert result["status"] == "ready", result["blockers"]
    assert result["schema_ready"] is True
    assert result["migration_ready"] is True
    assert contract["version"] != LEGACY_VERSION
    assert adapter.ledger[0] == LEGACY_ROW
    assert len(adapter.ledger) == 2
    assert adapter.ledger[1]["version"] == contract["version"]
    assert adapter.ledger[1]["contract_sha256"] == contract["contract_sha256"]

    # Rechecking the same catalog updates only the current verification timestamp.
    applied_at = adapter.ledger[1]["applied_at"]
    monkeypatch.setattr(readiness, "_now", lambda: "2026-09-08T21:01:00Z")
    repeated = readiness.verify_storage_schema(_FakeStore(adapter))
    assert repeated["status"] == "ready"
    assert len(adapter.ledger) == 2
    assert adapter.ledger[0] == LEGACY_ROW
    assert adapter.ledger[1]["applied_at"] == applied_at
    assert adapter.ledger[1]["verified_at"] == "2026-09-08T21:01:00Z"


def test_new_version_cannot_credit_missing_scanner_artifact_table():
    adapter = _FakePostgresAdapter()
    adapter.catalog.pop("scanner_raw_artifacts")
    adapter.ledger.append(deepcopy(LEGACY_ROW))

    result = readiness.verify_storage_schema(_FakeStore(adapter))

    assert result["status"] == "blocked"
    assert result["schema_ready"] is False
    assert result["catalog"]["missing_tables"] == ["scanner_raw_artifacts"]
    assert "schema_catalog_incomplete" in result["blockers"]
    assert adapter.ledger[0]["contract_sha256"] == LEGACY_HASH
