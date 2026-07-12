from __future__ import annotations

from copy import deepcopy

from nico.scanner_recovery_status import scanner_recovery_status


class _Store:
    def __init__(self, records, *, durable=True):
        self.records = deepcopy(records)
        self.durable = durable

    def status(self):
        return {
            "adapter": "postgres" if self.durable else "memory",
            "persistence_available": self.durable,
        }

    def list(self, table):
        assert table == "scanner_runs"
        return deepcopy(self.records)


def test_recovery_status_is_clear_when_no_interrupted_or_stale_scanners_exist(monkeypatch) -> None:
    monkeypatch.setenv("NICO_SCANNER_RECOVERY_STALE_SECONDS", "600")
    store = _Store(
        [
            {
                "scan_id": "scan_complete123456",
                "status": "complete",
                "updated_at": "2026-07-12T20:00:00Z",
            }
        ]
    )

    result = scanner_recovery_status(store)

    assert result["status"] == "clear"
    assert result["clear"] is True
    assert result["recovery_required"] == 0
    assert result["stale_active"] == 0


def test_recovery_status_reports_recovery_required_records() -> None:
    store = _Store(
        [
            {
                "scan_id": "scan_recovery12345",
                "status": "recovery_required",
                "updated_at": "2026-07-12T20:00:00Z",
            }
        ]
    )

    result = scanner_recovery_status(store)

    assert result["status"] == "attention_required"
    assert result["clear"] is False
    assert result["recovery_required"] == 1
    assert result["client_delivery_allowed"] is False


def test_recovery_status_is_unavailable_without_durable_postgres() -> None:
    result = scanner_recovery_status(_Store([], durable=False))

    assert result["status"] == "unavailable"
    assert result["clear"] is False
    assert result["blockers"] == ["durable_postgres_required"]
