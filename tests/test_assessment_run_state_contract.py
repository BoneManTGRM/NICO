from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps" / "web" / "app" / "assessment" / "runState.ts"


def test_run_state_rejects_backward_progress_and_stage_regression() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "incomingRank < previousRank" in source
    assert "incomingProgress < previousProgress" in source
    assert "incomingIsOlder" in source
    assert "return previous" in source


def test_terminal_state_cannot_be_overwritten_by_running_payload() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "isTerminalRun(previous) && !isTerminalRun(incoming)" in source


def test_truth_gate_has_bounded_stall_detection() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert 'activeStep(snapshot) === "truth_and_review_gates"' in source
    assert "5 * 60 * 1000" in source
    assert "truthGateHasStalled" in source


def test_customer_facing_name_does_not_use_raw_run_id() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "friendlyAssessmentName" in source
    assert "Express Assessment" in source
    assert "Mid Assessment" in source
    assert "Full Assessment" in source
    function_body = source.split("export function friendlyAssessmentName", 1)[1]
    assert "run_id" not in function_body
