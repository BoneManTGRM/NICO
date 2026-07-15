from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESILIENCE = ROOT / "apps" / "web" / "app" / "AssessmentStatusResilience.tsx"
SAVED_RUN_GUARD = ROOT / "apps" / "web" / "app" / "AssessmentSavedMidRunGuard.tsx"
OUTCOME_GUARD = ROOT / "apps" / "web" / "app" / "AssessmentStatusOutcomeGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"


def test_status_resilience_retries_only_exact_run_status_requests() -> None:
    source = RESILIENCE.read_text(encoding="utf-8")

    assert "STATUS_MAX_CONSECUTIVE_FAILURES = 8" in source
    assert "STATUS_RETRY_BASE_MS = 1500" in source
    assert "STATUS_RETRY_MAX_MS = 12000" in source
    assert "new Set([408, 425, 429, 500, 502, 503, 504])" in source
    assert "STATUS_PATH" in source
    assert "START_PATH" in source
    assert "for (let failure = 0; failure < STATUS_MAX_CONSECUTIVE_FAILURES" in source
    assert 'credentials: "same-origin"' in source
    assert "keepalive: true" in source

    status_section = source.split("if (!statusMatch", 1)[1]
    assert "originalFetch(nextInput" in status_section
    assert "START_PATH" not in status_section
    assert "Run ${" not in status_section


def test_one_transport_or_json_failure_does_not_become_a_failed_assessment() -> None:
    source = RESILIENCE.read_text(encoding="utf-8")

    assert "if (response.ok && !payload)" in source
    assert "RETRYABLE_HTTP_STATUSES.has(response.status)" in source
    assert "await sleep(retryDelay(failure + 1))" in source
    assert "temporarilyUnreachable(lastGood, runId)" in source
    assert 'output.status = "running"' in source
    assert "Exact run ${runId} remains preserved" in source
    assert "duplicate_start_allowed: false" in source


def test_nonterminal_status_http_error_is_not_converted_into_a_failed_run() -> None:
    source = OUTCOME_GUARD.read_text(encoding="utf-8")

    assert "function recoveryResponse" in source
    assert "without exact-run terminal evidence" in source
    assert 'output.status = "running"' in source
    assert 'status: "request_rejected"' in source
    assert "http_status: response.status" in source
    assert "exact_run_terminal_evidence: false" in source
    assert "duplicate_start_allowed: false" in source
    assert "return recoveryResponse(runId, response, payload, lastGoodByRun.get(runId))" in source


def test_exact_terminal_status_response_still_passes_through_unchanged() -> None:
    source = OUTCOME_GUARD.read_text(encoding="utf-8")

    assert 'TERMINAL_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"])' in source
    terminal_line = "if (identity.runId === runId && TERMINAL_STATUSES.has(identity.status)) return response"
    assert terminal_line in source
    assert source.index(terminal_line) < source.index("return recoveryResponse(runId, response, payload, lastGoodByRun.get(runId))")


def test_saved_mid_run_is_checked_before_any_new_start_request() -> None:
    source = RESILIENCE.read_text(encoding="utf-8")

    assert 'MID_ACTIVE_RUN_KEY = "nico.mid.active_run"' in source
    assert "savedRunId.startsWith(\"midrun_\")" in source
    assert "savedStatusUrl" in source
    assert "await resilientFetch(savedStatusUrl" in source
    assert "savedRunUnavailable(savedRunId, body)" in source
    assert "NICO did not start a duplicate assessment" in source

    start_block = source.split("if (startMatch)", 1)[1].split("// Assessment starts remain single-shot", 1)[0]
    assert "savedStatusUrl" in start_block
    assert "originalFetch(input, init)" not in start_block


def test_saved_mid_guard_uses_a_bounded_status_probe_contract() -> None:
    source = SAVED_RUN_GUARD.read_text(encoding="utf-8")

    assert "function statusProbeBody" in source
    assert 'repository: String(body.repository || "")' in source
    assert 'customer_id: String(body.customer_id || "default_customer")' in source
    assert 'project_id: String(body.project_id || "default_project")' in source
    assert "authorization_confirmed: true" in source
    assert "authorized: true" in source
    assert "auto_continue: true" in source
    assert "body: JSON.stringify(statusProbeBody(body))" in source


def test_terminal_saved_mid_run_is_preserved_then_replaced_in_the_same_click() -> None:
    source = SAVED_RUN_GUARD.read_text(encoding="utf-8")

    assert 'FAILURE_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"])' in source
    assert "exactTerminalFailure" in source
    assert "exactTerminalSuccess" in source
    terminal_block = source.split("if (exactTerminalFailure || exactTerminalSuccess)", 1)[1].split("if (statusResponse.ok", 1)[0]
    assert "rememberTerminalRun(savedRunId, payload)" in terminal_block
    assert "clearSavedRun(savedRunId)" in terminal_block
    assert "return originalFetch(input, init)" in terminal_block
    assert "return statusResponse" not in terminal_block
    assert 'MID_LAST_TERMINAL_RUN_KEY = "nico.mid.last_terminal_run"' in source


def test_unreachable_saved_mid_run_still_blocks_duplicate_start() -> None:
    source = SAVED_RUN_GUARD.read_text(encoding="utf-8")

    assert "safeUnavailableResponse(savedRunId, body)" in source
    assert "did not create a duplicate assessment" in source
    assert "duplicate_start_allowed: false" in source


def test_exact_run_terminal_evidence_is_never_retried_into_a_pass() -> None:
    source = RESILIENCE.read_text(encoding="utf-8")

    assert 'TERMINAL_STATUSES = new Set(["blocked", "failed", "error", "interrupted", "rejected"])' in source
    assert "responseRunId === runId && TERMINAL_STATUSES.has(status)" in source
    assert "if (matchingTerminalEvidence(payload, runId)) return response" in source


def test_scanner_progress_moves_inside_the_scanner_stage_instead_of_staying_at_42() -> None:
    source = RESILIENCE.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    assert "scannerProgress(payload" in source
    assert "scanner.progress_percent" in source
    assert "activeEvidence.scanner_progress_percent" in source
    assert "18 + (scanPercent * 0.43)" in source
    assert "Math.min(61" in source
    assert "scanner_progress_percent" in source
    assert "scanner_worker: 42" in page  # the resilience layer replaces this fallback with live evidence.


def test_resilience_wrappers_are_installed_before_transport_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentStatusResilience from "./AssessmentStatusResilience"' in layout
    assert 'import AssessmentSavedMidRunGuard from "./AssessmentSavedMidRunGuard"' in layout
    assert 'import AssessmentStatusOutcomeGuard from "./AssessmentStatusOutcomeGuard"' in layout
    assert "<AssessmentStatusResilience />" in layout
    assert "<AssessmentSavedMidRunGuard />" in layout
    assert "<AssessmentStatusOutcomeGuard />" in layout
    assert layout.index("<AssessmentStatusResilience />") < layout.index("<AssessmentSavedMidRunGuard />")
    assert layout.index("<AssessmentSavedMidRunGuard />") < layout.index("<AssessmentStatusOutcomeGuard />")
    assert layout.index("<AssessmentStatusOutcomeGuard />") < layout.index("<AssessmentApiTransportBridge />")
