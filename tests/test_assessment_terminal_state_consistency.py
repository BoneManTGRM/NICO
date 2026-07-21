from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentStatusOutcomeGuard.tsx"
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


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


def test_terminal_projection_never_displays_active_scanner_or_report() -> None:
    source = GUARD.read_text(encoding="utf-8")

    assert 'ACTIVE_STATUSES.has(String(scanner.status || "").toLowerCase())' in source
    assert 'status: "interrupted"' in source
    assert 'current_stage: "interrupted"' in source
    assert 'scanner_status: "interrupted"' in source
    assert 'output.report_generation_status = terminalStatus === "blocked" || terminalStatus === "rejected" ? "blocked" : "failed"' in source
    assert 'This stage did not complete because the exact run became ${terminalStatus}' in source
    assert 'RETAINED_TERMINAL_FIELDS' in source
    assert '"scanner"' in source
    assert '"reports"' in source


def test_unified_workspace_consumes_structured_terminal_state_instead_of_stale_result() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    guard = GUARD.read_text(encoding="utf-8")

    assert 'current = await json(await fetch' in workspace
    assert '["failed", "blocked", "error", "rejected", "interrupted"].includes(value)' in workspace
    assert 'return jsonResponse(output);' in guard
    assert 'output.run_id = runId' in guard
    assert 'output.progress = normalizedProgress' in guard
