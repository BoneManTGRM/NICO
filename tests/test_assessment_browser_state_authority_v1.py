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

    assert "const retryDelays = readinessPreflight" in source
    assert (
        ": runStatusRequest\n"
        "      ? CLIENT_RETRY_DELAYS_MS\n"
        "      : mutatingRequest\n"
        "        ? [0]\n"
        "        : CLIENT_RETRY_DELAYS_MS"
    ) in source
    assert "async function requestExactRunStatusWithRetry" in source
    assert 'return requestWithRetry(path, {method: "GET"}, copy);' in source
    assert "Exact-run GET retrying is centralized in requestWithRetry" in source
    assert "including Safari resume and Check again" in source
    assert "status is idempotent durable recovery truth" in source
    assert "No mutation is safely replayable" in source


def test_terminal_continuation_is_confirmed_by_exact_run_status() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "function statusPathForContinuation(path: string): string" in source
    assert "if (runContinueRequest && result.terminal === true)" in source
    assert "Confirm every terminal" in source
    assert "requestExactRunStatusWithRetry(" in source
    assert "statusPathForContinuation(path)" in source


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


def test_human_approved_delivery_blocked_run_remains_terminal_without_continuation() -> None:
    authority = TERMINAL_AUTHORITY.read_text(encoding="utf-8")
    controller = RUN_CONTROLLER.read_text(encoding="utf-8")

    approved = authority.index('if (value === "approved")')
    complete = authority.index('return "complete"', approved)
    assert approved < complete
    assert "client_delivery_allowed" not in authority[approved:complete]
    terminal_gate = controller.index("const stable = terminal(service, recovered);")
    settled = controller.index("if (stable)", terminal_gate)
    continuation = controller.index("await continueRun(recovered", settled)
    assert terminal_gate < settled < continuation
