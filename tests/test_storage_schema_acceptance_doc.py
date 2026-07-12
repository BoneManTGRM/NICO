from __future__ import annotations

from pathlib import Path


def test_storage_schema_acceptance_checklist_does_not_overclaim_restart_recovery() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "storage-schema-readiness-acceptance.md"
    text = path.read_text(encoding="utf-8").lower()

    assert "storage_schema_verified" in text
    assert "production release gate" in text
    assert "fresh mid run survives" in text
    assert "fresh full run survives" in text
    assert "next phase 3 implementation stage" in text
    assert "not claimed complete by schema verification alone" in text
