from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS_GUARD = ROOT / "apps" / "web" / "app" / "OperationsPreloadGuard.tsx"
ASSESSMENT_RECOVERY = ROOT / "apps" / "web" / "app" / "operations" / "AssessmentRecoveryPanel.tsx"
SCANNER_RECOVERY = ROOT / "apps" / "web" / "app" / "operations" / "ScannerRecoveryPanel.tsx"
BACKUP_RESTORE = ROOT / "apps" / "web" / "app" / "operations" / "backup-restore" / "page.tsx"


def test_operations_preload_hides_unrequested_evidence_without_false_failure_states() -> None:
    source = OPERATIONS_GUARD.read_text(encoding="utf-8")

    assert 'PRELOAD_SECTION_ATTRIBUTE = "data-nico-preload-section-hidden"' in source
    assert 'element.style.setProperty("display", "none", "important")' in source
    assert 'element.style.removeProperty("display")' in source
    assert "section.hidden" not in source
    assert "No readiness, release, storage, workload, incident, or alert state is inferred before authentication succeeds." in source
    assert 'authentication.textContent?.includes("Last loaded:") === true' in source


def test_assessment_recovery_uses_neutral_not_loaded_state_but_keeps_loaded_failures_red() -> None:
    source = ASSESSMENT_RECOVERY.read_text(encoding="utf-8")

    assert 'String(status || "not_loaded")' in source
    assert 'if (value === "not_loaded") return styles.neutral' in source
    assert 'return styles.bad' in source
    assert 'const loaded = inventory !== null' in source
    assert ': "Not loaded"' in source
    assert "Enter the admin token and load recovery" in source
    assert '["not_loaded", "unavailable"]' not in source


def test_scanner_recovery_uses_neutral_not_loaded_state_but_keeps_loaded_failures_red() -> None:
    source = SCANNER_RECOVERY.read_text(encoding="utf-8")

    assert 'String(status || "not_loaded")' in source
    assert 'if (value === "not_loaded") return styles.neutral' in source
    assert 'return styles.bad' in source
    assert 'const loaded = inventory !== null' in source
    assert ': "Not loaded"' in source
    assert "Enter the admin token and load recovery" in source
    assert '["not_loaded", "unavailable"]' not in source


def test_backup_restore_guardrail_remains_intentionally_strict() -> None:
    source = BACKUP_RESTORE.read_text(encoding="utf-8")

    assert 'summary?.status || "not checked"' in source
    assert 'return "status gray"' in source
    assert '<span className="status red">Never production</span>' in source
    assert "This interface does not create backups or execute restores." in source
