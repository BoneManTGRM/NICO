from __future__ import annotations

from pathlib import Path


def test_storage_schema_readiness_runbook_requires_safe_recovery() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "STORAGE_SCHEMA_READINESS.md"
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()

    for required in [
        "nico.storage_schema_readiness.v1",
        "2026.07.13.1",
        "nico_schema_migrations",
        "information_schema.columns",
        "get /operations/storage-schema",
        "storage_schema_verified",
        "x-nico-admin-token",
        "memory fallback",
        "production release gate",
        "fresh mid and full acceptance workflows",
        "backup",
        "rollback",
    ]:
        assert required in lowered

    for prohibited_claim in [
        "does not authorize client delivery",
        "does not prove that the required tables and columns exist",
        "green vercel or railway provider check does not override",
    ]:
        assert prohibited_claim in lowered

    assert "raw database messages are not retained" in lowered
    assert "never represented as durable or restart-safe" in lowered
