from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentFinalGateAuthoritativeGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_browser_stall_repair_never_claims_backend_completion() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "function usableReportArtifacts" in source
    assert 'const markdown = String(reports.markdown || "").trim()' in source
    assert 'const html = String(reports.html || "").trim()' in source
    assert 'const pdf = String(reports.pdf_base64 || "").trim()' in source
    assert "return Boolean(markdown && html && pdf)" in source
    assert 'output.status = "running"' in source
    assert 'output.current_stage = "truth_and_review_gates"' in source
    assert 'output.progress_percent = Math.max(94, Math.min(99' in source
    assert 'output.status = "complete"' not in source
    assert 'output.progress_percent = 100' not in source


def test_progress_label_or_status_alone_cannot_fabricate_a_report() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert "function reportGenerationComplete(payload: JsonRecord): boolean" in source
    assert "return usableReportArtifacts(payload)" in source
    assert 'report_generation_status || ""' not in source
    assert 'String(item.step || "").toLowerCase() === "report_generation"' not in source


def test_false_stall_repair_keeps_review_delivery_and_duplicate_controls_fail_closed() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'output.human_review_required = true' in source
    assert 'output.client_ready = false' in source
    assert 'output.client_delivery_allowed = false' in source
    assert 'output.delivery_status = "blocked_pending_backend_completion_and_human_review"' in source
    assert 'output.duplicate_start_allowed = false' in source
    assert 'output.recovery_required = false' in source


def test_repair_removes_only_browser_generated_stall_and_waits_for_backend() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'return code !== "assessment_final_gate_stalled"' in source
    assert 'code: "browser_final_gate_false_block_removed"' in source
    assert 'browser_projection_only: true' in source
    assert 'browser_terminalization_forbidden: true' in source
    assert 'terminal_state_written: false' in source
    assert 'exact_run_terminal_evidence: false' in source
    assert 'required_formats: ["markdown", "html", "pdf"]' in source
    assert "Waiting for the backend to persist the exact run's terminal completion state." in source


def test_authoritative_guard_wraps_progress_guard_before_api_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    assert 'import AssessmentFinalGateAuthoritativeGuard from "./AssessmentFinalGateAuthoritativeGuard"' in layout
    assert '<AssessmentFinalGateAuthoritativeGuard />' in layout
    assert layout.index('<AssessmentProgressIntegrityGuard />') < layout.index('<AssessmentFinalGateAuthoritativeGuard />')
    assert layout.index('<AssessmentFinalGateAuthoritativeGuard />') < layout.index('<AssessmentApiTransportBridge />')
