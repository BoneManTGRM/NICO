from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "operations" / "backup-restore" / "page.tsx"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_operations_navigation_exposes_backup_restore_verification() -> None:
    navigation = NAVIGATION.read_text(encoding="utf-8")

    assert '{label: "Backup & Restore", href: "/operations/backup-restore"}' in navigation
    assert 'pathname.startsWith("/operations")' in navigation


def test_operator_page_uses_complete_route_group() -> None:
    source = _page()

    assert "/operations/backup-restore?${query()}" in source
    assert "/operations/backup-restore/backup-evidence?${query()}" in source
    assert "/operations/backup-restore/restore-drill?${query()}" in source
    assert 'method: "POST"' in source
    assert '"X-NICO-Admin-Token": adminToken' in source


def test_admin_token_is_memory_only_and_not_added_to_urls_or_storage() -> None:
    source = _page()

    assert 'const [adminToken, setAdminToken] = useState("")' in source
    assert 'type="password"' in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.cookie" not in source
    assert 'new URLSearchParams({' in source
    query_block = source.split("function query()", 1)[1].split("async function readJson", 1)[0]
    assert "adminToken" not in query_block
    assert "actor" not in query_block


def test_page_does_not_offer_backup_creation_restore_execution_or_failover() -> None:
    source = _page()

    assert "This interface does not create backups or execute restores" in source
    assert "NICO did not create, access, or download a backup" in source
    assert "NICO did not execute a restore, failover, rollback, or production mutation" in source
    assert "Never production" in source
    assert "isolated non-production target" in source
    assert "Create backup" not in source
    assert "Execute restore" not in source
    assert "Fail over" not in source


def test_page_collects_only_bounded_evidence_fields() -> None:
    source = _page()

    for required in [
        "backup_reference_sha256",
        "encrypted_at_rest_verified",
        "separated_copy_verified",
        "retention_days",
        "pitr_window_hours",
        "source_backup_reference_sha256",
        "restored_record_set_sha256",
        "isolated_nonproduction_target_verified",
        "schema_contract_sha256",
        "required_tables_verified",
        "application_read_verified",
    ]:
        assert required in source

    for prohibited in [
        "database_url",
        "DATABASE_URL",
        "backup_url",
        "archive_contents",
        "connection_string",
        "provider_payload",
    ]:
        assert prohibited not in source


def test_raw_notes_are_described_as_hashed_and_not_retained() -> None:
    source = _page()

    assert "The note is hashed and not retained" in source
    assert "Notes are hashed and are not retained" in source
    assert "Do not include secrets or provider URLs" in source


def test_status_display_surfaces_schema_hash_blockers_and_safe_evidence() -> None:
    source = _page()

    assert "schema_contract_sha256" in source
    assert "latest_backup" in source
    assert "latest_restore_drill" in source
    assert "Blockers:" in source
    assert "Warnings:" in source
    assert "Safe evidence identity" in source
