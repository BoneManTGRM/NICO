from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "apps" / "web" / "app" / "AssessmentRunStateGuard.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
RUN_STATE = ROOT / "apps" / "web" / "app" / "assessment" / "runState.ts"
PRESENTATION = ROOT / "apps" / "web" / "app" / "ReportPresentationGuard.tsx"


def test_shared_guard_is_installed_before_assessment_transports() -> None:
    text = LAYOUT.read_text(encoding="utf-8")
    assert 'import AssessmentRunStateGuard from "./AssessmentRunStateGuard";' in text
    assert text.index("<AssessmentRunStateGuard />") < text.index("<AssessmentStatusResilience />")
    assert text.index("<AssessmentRunStateGuard />") < text.index("<AssessmentApiTransportBridge />")


def test_guard_covers_express_mid_and_full_status_routes() -> None:
    text = GUARD.read_text(encoding="utf-8")
    assert "(express|mid|full)-run" in text
    assert "reconcileRunSnapshot" in text
    assert "truthGateHasStalled" in text
    assert "window.fetch" in text


def test_guard_rejects_progress_regressions_and_terminalizes_stalls() -> None:
    guard = GUARD.read_text(encoding="utf-8")
    state = RUN_STATE.read_text(encoding="utf-8")
    assert "incomingProgress < previousProgress" in state
    assert "incomingRank < previousRank" in state
    assert 'status: "blocked"' in guard
    assert 'blocking_gate: "truth_and_review_gates_timeout"' in guard
    assert "last_successful_checkpoint" in guard
    assert "5 * 60 * 1000" in guard


def test_truth_gate_uses_canonical_backend_stage_before_progress_array() -> None:
    state = RUN_STATE.read_text(encoding="utf-8")
    assert 'const canonical = String(snapshot.current_stage || "")' in state
    assert "if (canonical) return canonical" in state
    assert 'canonicalStage === "truth_and_review_gates"' in state


def test_guard_preserves_audit_identity_and_does_not_fake_completion() -> None:
    text = GUARD.read_text(encoding="utf-8")
    assert "run_id" in text
    assert 'status: "complete"' not in text
    assert "human_review_required: true" in text


def test_raw_run_id_is_not_the_primary_customer_facing_heading() -> None:
    text = PRESENTATION.read_text(encoding="utf-8")
    assert "RAW_RUN_ID" in text
    assert "Technical run ID:" in text
    assert "Active authorized repository" in text
    assert 'element.matches("h1, h2, h3")' in text
    assert 'element.style.overflowWrap = "anywhere"' in text
