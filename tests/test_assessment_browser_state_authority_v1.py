from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = ROOT / "apps/web/app/assessment/assessmentRunRequests.ts"
TERMINAL_AUTHORITY = ROOT / "apps/web/app/assessment/assessmentTerminalAuthority.ts"
MODEL = ROOT / "apps/web/app/assessment/assessmentModel.ts"
TYPES = ROOT / "apps/web/app/assessment/assessmentTypes.ts"
RUN_CONTROLLER = ROOT / "apps/web/app/assessment/useAssessmentRun.ts"


def test_exact_run_status_retries_without_replaying_continuation() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "const retryDelays = runContinueRequest ? [0] : CLIENT_RETRY_DELAYS_MS;" in source
    assert "const retryDelays = boundedRequest ? [0] : CLIENT_RETRY_DELAYS_MS;" not in source
    assert "keep continuation strictly single-attempt" in source
    assert "retry only the idempotent readiness/status reads" in source


def test_terminal_continuation_is_confirmed_by_exact_run_status() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "function statusPathForContinuation(path: string): string" in source
    assert "if (runContinueRequest && result.terminal === true)" in source
    assert "Confirm every terminal" in source
    assert "statusPathForContinuation(path)" in source
    assert '{method: "GET"}' in source


def test_created_run_transport_uncertainty_is_not_promoted_to_run_failure() -> None:
    source = REQUESTS.read_text(encoding="utf-8")
    guard = source.index("if (runCreated) {")
    service_unavailable = source.index('kind: "service_unavailable"', guard)
    run_failed = source.index('kind: "run_failed"', guard)

    assert service_unavailable < run_failed
    assert "A request/control-plane error after intake is not authoritative evidence" in source
    assert "message: copy.runStatusUnavailableMessage" in source[guard:run_failed]
    assert "retryable: true" in source[guard:run_failed]


def test_browser_terminal_phase_requires_explicit_canonical_marker() -> None:
    authority = TERMINAL_AUTHORITY.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    controller = RUN_CONTROLLER.read_text(encoding="utf-8")

    marker_guard = authority.index("if (result.terminal !== true) {")
    status_projection = authority.index("const value =", marker_guard)
    assert marker_guard < status_projection
    assert "return null;" in authority[marker_guard:status_projection]
    assert 'export {terminal} from "./assessmentTerminalAuthority";' in model
    assert "terminal?: boolean;" in types
    assert 'terminal, wait} from "./assessmentModel"' in controller
