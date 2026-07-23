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
    assert '"assessment_completion", "express_completion"' in source


def test_report_and_review_readiness_cannot_complete_a_running_backend_run() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "FINAL_GATE_MIN_PERCENT = 94" in source
    assert "reportReady(payload, tier) && reviewReady(payload, tier)" in source
    assert "hasSupportingCompletionEvidence" in source
    assert "return waitingProjection(payload, state, tier)" in source
    assert 'output.status = "running"' in source
    assert 'output.current_stage = "truth_and_review_gates"' in source
    assert 'browser_terminalization_forbidden: true' in source
    assert 'output.status = "complete"' not in source
    assert 'output.progress_percent = 100' not in source


def test_backend_top_level_terminal_status_is_the_only_polling_stop_condition() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "if (TERMINAL.has(status))" in source
    assert "Only the backend's top-level exact-run status may end polling" in source
    assert source.index("if (TERMINAL.has(status))") < source.index("const atFinalGate")
    assert 'status === "complete" || status === "completed"' in source
    assert 'state.highestStage = "complete"' in source


def test_completion_subdocument_is_supporting_evidence_not_terminal_authority() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "function completionEvidenceReady" in source
    assert 'completion.report_formats_ready === true' in source
    assert 'completion.score_ready === true' in source
    assert 'completion.sections_ready === true' in source
    assert 'completion.human_review_required === true' in source
    assert "completion_contract_present" in source
    assert "exact_run_terminal_evidence: false" in source


def test_browser_poll_threshold_is_diagnostic_and_never_terminalizes_run() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "FINAL_GATE_MAX_POLLS = 20" in source
    assert "state.finalGatePolls += 1" in source
    assert "state.finalGatePolls >= FINAL_GATE_MAX_POLLS" in source
    assert 'code: "assessment_final_gate_waiting"' in source
    assert 'status: "running"' in source
    assert 'browser_terminalization_forbidden: true' in source
    assert 'recovery_required: false' in source
    assert 'output.status = "blocked"' not in source
    assert 'output.current_stage = "recovery_required"' not in source
    assert 'output.recovery_path = "/operations/recovery"' not in source


def test_waiting_projection_preserves_backend_truth_and_exact_run_identity() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert "const output = structuredClone(payload)" in source
    assert 'output.duplicate_start_allowed = false' in source
    assert 'exact_run_terminal_evidence: false' in source
    assert 'terminal_state_written: false' in source
    assert "without starting a duplicate assessment" in source


def test_progress_guard_wraps_native_status_and_recovery_normalizers_before_api_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentProgressIntegrityGuard from "./AssessmentProgressIntegrityGuard"' in layout
    assert '<AssessmentProgressIntegrityGuard />' in layout
    assert "AssessmentMidLiveStatusTransport" not in layout
    assert "AssessmentSavedMidRunGuard" not in layout
    assert layout.index('<AssessmentStatusOutcomeGuard />') < layout.index('<AssessmentExpressRecoveryGuard />')
    assert layout.index('<AssessmentExpressRecoveryGuard />') < layout.index('<AssessmentProgressIntegrityGuard />')
    assert layout.index('<AssessmentProgressIntegrityGuard />') < layout.index('<AssessmentApiTransportBridge />')
