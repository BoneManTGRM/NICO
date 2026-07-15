from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESILIENCE = ROOT / "apps" / "web" / "app" / "AssessmentStatusResilience.tsx"
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


def test_resilience_wrapper_is_installed_before_transport_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import AssessmentStatusResilience from "./AssessmentStatusResilience"' in layout
    assert "<AssessmentStatusResilience />" in layout
    assert layout.index("<AssessmentStatusResilience />") < layout.index("<AssessmentApiTransportBridge />")
