from __future__ import annotations

from nico.storage_schema_readiness import storage_schema_contract


def test_storage_schema_contract_contains_structure_only() -> None:
    contract = storage_schema_contract()
    rendered = repr(contract).lower()

    for forbidden in [
        "database_url",
        "password_hash",
        "raw_token",
        "access_token",
        "cookie_value",
        "api_key_value",
        "private_key_value",
        "provider_response",
    ]:
        assert forbidden not in rendered

    assert set(contract) == {
        "version",
        "tables",
        "migration_table",
        "contract_sha256",
    }
    assert "authorized_repositories" in contract["tables"]
    assert "authorization_scope" in contract["tables"]["authorized_repositories"]
