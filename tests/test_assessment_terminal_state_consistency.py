from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentStatusOutcomeGuard.tsx"
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"


def test_non_terminal_exact_run_status_outage_remains_running() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'status: "temporarily_unreachable"' in source
    assert 'output.status = "running"' in source
    assert 'exact_run_terminal_evidence: false' in source
    assert 'duplicate_start_allowed: false' in source
    assert 'NICO will continue read-only checks without starting a duplicate assessment' in source
    assert 'if (!lastGood) throw error;' in source
    assert 'new Response(null, {status: 503, statusText: "Status transport interrupted"})' in source
    assert 'return recoveryResponse(runId, response, payload, lastGoodByRun.get(runId));' in source
    assert 'if (EXPRESS_STATUS_PATH.test(url.pathname)) return response;' not in source


def test_exact_terminal_payload_is_returned_as_structured_success_for_page_state() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'function terminalResponse(' in source
    assert 'identity.runId === runId && TERMINAL_STATUSES.has(identity.status)' in source
    assert 'return terminalResponse(runId, response, payload, lastGoodByRun.get(runId));' in source
    assert 'status: 200' in source
    assert 'status: "exact_run_terminal"' in source
    assert 'exact_run_terminal_evidence: true' in source
    assert 'output.status = terminalStatus' in source
    assert 'output.progress_percent = 100' in source
    assert 'output.client_ready = false' in source


def test_terminal_projection_preserves_one_failed_stage_and_truthful_artifact_state() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'function normalizeTerminalProgress(' in source
    assert 'const {backendStage, uiStage} = terminalStages(output);' in source
    assert 'if (index === failedIndex)' in source
    assert 'status: terminalStatus' in source
    assert 'if (IN_FLIGHT_STATUSES.has(itemStatus))' in source
    assert 'return {...item, status: "pending"};' in source
    assert 'Pending and planned stages did not execute.' in source
    assert 'IN_FLIGHT_STATUSES.has(String(scanner.status || "").toLowerCase())' in source
    assert 'status: "interrupted"' in source
    assert 'current_stage: "interrupted"' in source
    assert 'scanner_status: "interrupted"' in source
    assert 'output.report_generation_status = terminalStatus === "blocked" || terminalStatus === "rejected" ? "blocked" : "failed"' in source
    assert 'RETAINED_TERMINAL_FIELDS' in source
    assert '"scanner"' in source
    assert '"reports"' in source


def test_unified_workspace_consumes_structured_terminal_state_instead_of_stale_result() -> None:
    controller = (ASSESSMENT / "useAssessmentRun.ts").read_text(encoding="utf-8")
    model = (ASSESSMENT / "assessmentModel.ts").read_text(encoding="utf-8")
    guard = GUARD.read_text(encoding="utf-8")
    assert 'const continued = await requestWithRetry(' in controller
    assert 'current = preserveRunIdentity(continued' in controller
    assert 'const stable = terminal(service, current)' in controller
    assert 'setResult(current)' in controller
    assert '["failed", "blocked", "error", "rejected", "interrupted"].includes(value)' in model
    assert 'return jsonResponse(output);' in guard
    assert 'output.run_id = runId' in guard
    assert 'output.progress = normalizeTerminalProgress(' in guard
    assert 'output.current_stage = String(output.failure_ui_stage || output.failure_stage || terminalStatus)' in guard
