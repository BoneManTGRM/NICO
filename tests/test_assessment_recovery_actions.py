from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ROOT / "apps" / "web" / "app" / "AssessmentRecoveryActions.tsx"
TRANSPORT = ROOT / "apps" / "web" / "app" / "AssessmentMidLiveStatusTransport.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
RECOVERY_PAGE = ROOT / "apps" / "web" / "app" / "operations" / "recovery" / "page.tsx"
ASSESSMENT_PANEL = ROOT / "apps" / "web" / "app" / "operations" / "AssessmentRecoveryPanel.tsx"
SCANNER_PANEL = ROOT / "apps" / "web" / "app" / "operations" / "ScannerRecoveryPanel.tsx"


def test_live_status_failure_publishes_visible_bounded_diagnostics() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")

    assert 'MID_RECOVERY_STATE_EVENT = "nico:mid-recovery-state"' in source
    assert 'MID_FORCE_LIVE_RETRY_EVENT = "nico:mid-live-status-retry"' in source
    assert "LIVE_BACKOFF_BASE_MS = 3_000" in source
    assert "LIVE_BACKOFF_MAX_MS = 30_000" in source
    assert "consecutiveFailures" in source
    assert "nextProbeAt" in source
    assert "backend_contract_mismatch" in source
    assert "duplicate_start_allowed: false" in source
    assert 'window.sessionStorage.setItem("nico.mid.recovery_state"' in source


def test_recovery_actions_include_manual_retry_exact_recovery_operations_and_diagnostics() -> None:
    source = ACTIONS.read_text(encoding="utf-8")

    assert "Retry live status now" in source
    assert "Recover exact scanner" in source
    assert "Inspect Recovery Control" in source
    assert "Open Operations" in source
    assert "Copy diagnostics" in source
    assert "Do not start another Mid assessment" in source
    assert "run_id" in source
    assert "scan_id" in source
    assert "heartbeat_at" in source
    assert "last_success_at" in source


def test_recovery_actions_are_mounted_globally_after_transport() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentRecoveryActions from "./AssessmentRecoveryActions"' in layout
    assert "<AssessmentRecoveryActions />" in layout
    assert layout.index("<AssessmentMidLiveStatusTransport />") < layout.index("<AssessmentRecoveryActions />")


def test_recovery_page_accepts_exact_run_and_scanner_query_targets() -> None:
    page = RECOVERY_PAGE.read_text(encoding="utf-8")
    assessment = ASSESSMENT_PANEL.read_text(encoding="utf-8")
    scanner = SCANNER_PANEL.read_text(encoding="utf-8")

    assert 'params.get("run_id")' in page
    assert 'params.get("scan_id")' in page
    assert "targetRunId={targetRunId}" in page
    assert "targetScanId={targetScanId}" in page
    assert "Exact recovery target" in page
    assert "assessment-recovery-${targetRunId}" in assessment
    assert "scanner-recovery-${targetScanId}" in scanner
    assert "Resume same run ID" in assessment
    assert "Resume same scan ID" in scanner
