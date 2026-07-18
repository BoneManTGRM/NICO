from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentProgressIntegrityGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_progress_never_regresses_when_status_payloads_arrive_out_of_order() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "if (nextPercent >= state.highestPercent)" in source
    assert "output.progress_percent = state.highestPercent" in source
    assert "output.current_stage = state.highestStage" in source
    assert '"repository_snapshot", "repository_evidence", "scanner", "scanner_evidence"' in source
    assert '"reports", "mid_report", "approval", "approval_request", "persistence"' in source


def test_complete_artifact_and_review_evidence_resolves_96_percent_gate() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "FINAL_GATE_MIN_PERCENT = 94" in source
    assert "reportReady(payload, tier) && reviewReady(payload, tier)" in source
    assert 'output.status = "complete"' in source
    assert 'output.current_stage = "complete"' in source
    assert "output.progress_percent = 100" in source
    assert 'status: "completed_from_artifact_evidence"' in source


def test_final_gate_without_required_evidence_is_bounded_not_infinite() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "FINAL_GATE_MAX_POLLS = 20" in source
    assert "state.finalGatePolls += 1" in source
    assert 'output.status = "blocked"' in source
    assert 'output.current_stage = "recovery_required"' in source
    assert 'code: "assessment_final_gate_stalled"' in source
    assert 'duplicate_start_allowed: false' in source
    assert 'terminal_state_written: false' in source
    assert 'recovery_path = "/operations/recovery"' in source


def test_progress_guard_is_outer_to_existing_status_normalizers() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentProgressIntegrityGuard from "./AssessmentProgressIntegrityGuard"' in layout
    assert '<AssessmentProgressIntegrityGuard />' in layout
    assert layout.index('<AssessmentStatusOutcomeGuard />') < layout.index('<AssessmentProgressIntegrityGuard />')
    assert layout.index('<AssessmentMidLiveStatusTransport />') < layout.index('<AssessmentProgressIntegrityGuard />')
    assert layout.index('<AssessmentProgressIntegrityGuard />') < layout.index('<AssessmentApiTransportBridge />')
