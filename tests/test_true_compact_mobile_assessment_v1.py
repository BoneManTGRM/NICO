from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (ROOT / "apps/web/app/assessment/AssessmentWorkspace.tsx").read_text(encoding="utf-8")
MODE_HOOK = (ROOT / "apps/web/app/assessment/useAssessmentClientMode.ts").read_text(encoding="utf-8")
COMPACT_CSS = (ROOT / "apps/web/app/assessment/compactMobileAssessment.module.css").read_text(encoding="utf-8")
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")


def test_mobile_mode_fails_closed_before_hydration() -> None:
    assert "compactMobile: true" in MODE_HOOK
    assert "hydrated: false" in MODE_HOOK
    assert "(max-width: 1024px), (pointer: coarse)" in MODE_HOOK


def test_workspace_exposes_hydration_and_client_mode_contract() -> None:
    assert 'data-assessment-hydrated={hydrated ? "true" : "false"}' in WORKSPACE
    assert 'data-assessment-client-mode={compactMobile ? "compact-mobile" : "full"}' in WORKSPACE
    assert 'data-mobile-compact-terminal="true"' in WORKSPACE
    assert 'data-mobile-heavy-report-mounted="false"' in WORKSPACE
    assert 'data-full-assessment-details="true"' in WORKSPACE


def test_mobile_branch_does_not_mount_desktop_report_details() -> None:
    compact_start = WORKSPACE.index('{compactMobile ? <div')
    desktop_start = WORKSPACE.index(': <div data-full-assessment-details="true">', compact_start)
    compact_branch = WORKSPACE[compact_start:desktop_start]
    assert "<ProgressTimeline" not in compact_branch
    assert "<Scorecard" not in compact_branch
    assert "executive_summary" not in compact_branch
    assert "unavailable_data_notes" not in compact_branch
    assert "data-assessment-report-actions" not in compact_branch or "{reportActions}" in compact_branch


def test_mobile_intake_does_not_mount_strategic_editor() -> None:
    assert 'data-mobile-evidence-boundary="true"' in WORKSPACE
    assert 'data-evidence-editor-mounted="false"' in WORKSPACE
    assert 'compactMobile ? <section' in WORKSPACE
    assert ': <StrategicEvidenceForm' in WORKSPACE


def test_compact_terminal_uses_containment_and_no_scroll_anchor() -> None:
    assert "contain: layout paint style" in COMPACT_CSS
    assert "overflow-anchor: none" in COMPACT_CSS
    assert "box-shadow: none" in COMPACT_CSS


def test_browser_proof_waits_for_hydration_and_rejects_heavy_dom() -> None:
    assert 'data-assessment-hydrated="true"' in PROOF
    assert 'data-assessment-client-mode="compact-mobile"' in PROOF
    assert "full_detail_count" in PROOF
    assert "stage_history_count" in PROOF
    assert "scorecard_grid_count" in PROOF
    assert "node_count" in PROOF
    assert 'compact_mobile_dom_verified' in PROOF
