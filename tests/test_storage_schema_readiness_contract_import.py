from __future__ import annotations

from nico.storage_schema_readiness import storage_schema_contract


def test_storage_schema_contract_contains_structure_only() -> None:
    contract = storage_schema_contract()
    rendered = repr(contract).lower()

    for forbidden in [
        "database_url",
        "password",
        "authorization",
        "cookie",
        "api_key",
        "secret",
        "provider_response",
    ]:
        assert forbidden not in rendered

    assert set(contract) == {"version", "tables", "migration_table", "contract_sha256"}
