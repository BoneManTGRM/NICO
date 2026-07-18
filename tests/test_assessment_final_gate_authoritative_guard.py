from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentFinalGateAuthoritativeGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def test_report_generation_completion_is_authoritative_over_browser_stall() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'String(item.step || "").toLowerCase() === "report_generation"' in source
    assert 'String(item.status || "").toLowerCase() === "complete"' in source
    assert 'String(transport.code || "").toLowerCase() === "assessment_final_gate_stalled"' in source
    assert 'String(record(item.evidence).code || "").toLowerCase() === "assessment_final_gate_stalled"' in source
    assert "if (!reportGenerationComplete(payload) || payload.human_review_required !== true) return payload" in source
    assert 'output.status = "complete"' in source
    assert 'output.progress_percent = 100' in source


def test_repair_keeps_human_review_and_delivery_controls_fail_closed() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'output.human_review_required = true' in source
    assert 'output.client_ready = false' in source
    assert 'output.client_delivery_allowed = false' in source
    assert 'output.delivery_status = "blocked_pending_human_review"' in source


def test_repair_removes_only_browser_generated_stall_evidence() -> None:
    source = GUARD.read_text(encoding="utf-8")
    assert 'return code !== "assessment_final_gate_stalled"' in source
    assert 'code: "browser_final_gate_false_block_repaired"' in source
    assert 'browser_projection_only: true' in source
    assert 'terminal_state_written: false' in source


def test_authoritative_guard_wraps_progress_guard_before_api_bridge() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    assert 'import AssessmentFinalGateAuthoritativeGuard from "./AssessmentFinalGateAuthoritativeGuard"' in layout
    assert '<AssessmentFinalGateAuthoritativeGuard />' in layout
    assert layout.index('<AssessmentProgressIntegrityGuard />') < layout.index('<AssessmentFinalGateAuthoritativeGuard />')
    assert layout.index('<AssessmentFinalGateAuthoritativeGuard />') < layout.index('<AssessmentApiTransportBridge />')
