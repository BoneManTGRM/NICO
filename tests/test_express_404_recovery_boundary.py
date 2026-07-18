from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentExpressRecoveryGuard.tsx"
ACTIONS = ROOT / "apps" / "web" / "app" / "AssessmentExpressRecoveryActions.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_express_404_is_bounded_and_never_left_indefinitely_running() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert 'FAILURE_LIMIT = 3' in source
    assert 'FAILURE_WINDOW_MS = 30_000' in source
    assert 'status === 404' in source
    assert 'code === "http_404"' in source
    assert 'if (!persistence.durable || exhausted)' in source
    assert 'output.status = "blocked"' in source
    assert 'output.current_stage = "recovery_required"' in source
    assert 'status: "recovery_required"' in source
    assert 'duplicate_start_allowed: false' in source
    assert 'terminal_state_written: false' in source
    assert 'exact_run_terminal_evidence: false' in source


def test_non_durable_missing_run_escalates_immediately() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert 'persistence.durable === true' in source
    assert 'A 404 combined with an explicitly non-durable record' in source
    assert 'Recover or explicitly close this run before starting another assessment.' in source
    assert 'status_read_only = true' in source
    assert 'human_review_required = true' in source
    assert 'client_ready = false' in source


def test_visible_express_recovery_control_preserves_exact_run_identity() -> None:
    source = ACTIONS.read_text(encoding="utf-8")

    assert 'EXPRESS RUN CONTROL' in source
    assert 'Exact-run recovery required' in source
    assert 'url.searchParams.set("run_id", state.run_id)' in source
    assert 'url.searchParams.set("tier", "express")' in source
    assert 'Do not start another Express assessment yet.' in source
    assert 'Open exact-run Recovery' in source
    assert 'Copy diagnostics' in source


def test_express_recovery_guard_wraps_outcome_guard_before_api_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentExpressRecoveryGuard from "./AssessmentExpressRecoveryGuard"' in layout
    assert 'import AssessmentExpressRecoveryActions from "./AssessmentExpressRecoveryActions"' in layout
    assert '<AssessmentExpressRecoveryGuard />' in layout
    assert '<AssessmentExpressRecoveryActions />' in layout
    assert layout.index('<AssessmentStatusOutcomeGuard />') < layout.index('<AssessmentExpressRecoveryGuard />')
    assert layout.index('<AssessmentExpressRecoveryGuard />') < layout.index('<AssessmentMidLiveStatusTransport />')
    assert layout.index('<AssessmentExpressRecoveryGuard />') < layout.index('<AssessmentApiTransportBridge />')
