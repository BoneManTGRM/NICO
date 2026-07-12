from __future__ import annotations

from pathlib import Path


def test_scanner_recovery_runbook_preserves_safety_boundaries() -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "SCANNER_RECOVERY.md").read_text(encoding="utf-8").lower()

    for required in [
        "recovery_required",
        "nico_scanner_recovery_stale_seconds",
        "get /operations/recovery",
        "post /operations/recovery/scanner/{scan_id}/resume",
        "x-nico-admin-token",
        "atomic postgres transition",
        "same scan id",
        "idempotent reuse",
        "scanner_recovery_queue_clear",
        "never starts a scanner automatically",
        "does not include scanner output",
        "client delivery",
    ]:
        assert required in text

    assert "does not yet prove" in text
    assert "backup creation or restore execution" in text
    assert "automatic mid or full run recovery" in text
