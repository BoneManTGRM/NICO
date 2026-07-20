from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES, EXPRESS_STAGES
from nico.comprehensive_stage_adapter import build_comprehensive_run_state, run_comprehensive_stages


def _state():
    return build_comprehensive_run_state(
        run_id="comprehensive_run_123",
        repository="BoneManTGRM/NICO",
        commit_sha="abc123",
        evidence_ledger_id="ledger_123",
        authorized=True,
    )


def _executor(context):
    return {"status": "complete", "evidence_count": len(context["prior_stage_results"])}


def test_adapter_executes_every_express_stage_before_deeper_stages() -> None:
    executors = {stage: _executor for stage in COMPREHENSIVE_STAGES}
    result = run_comprehensive_stages(_state(), executors)

    assert result["status"] == "review_required"
    assert tuple(result["completed_stages"][: len(EXPRESS_STAGES)]) == EXPRESS_STAGES
    assert tuple(result["completed_stages"]) == COMPREHENSIVE_STAGES
    assert result["progress_percent"] == 100.0
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_missing_executor_blocks_at_exact_required_stage() -> None:
    executors = {stage: _executor for stage in COMPREHENSIVE_STAGES if stage != "functional_qa"}
    result = run_comprehensive_stages(_state(), executors)

    assert result["status"] == "blocked"
    assert result["current_stage"] == "functional_qa"
    assert "missing_executor:functional_qa" in result["blockers"]
    assert "functional_qa" not in result["completed_stages"]


def test_failed_stage_stops_without_false_completion() -> None:
    executors = {stage: _executor for stage in COMPREHENSIVE_STAGES}
    executors["deep_scanner_triage"] = lambda context: {"status": "failed", "reason": "triage incomplete"}
    result = run_comprehensive_stages(_state(), executors)

    assert result["status"] == "blocked"
    assert result["current_stage"] == "deep_scanner_triage"
    assert "stage_failed:deep_scanner_triage:failed" in result["blockers"]
    assert "deep_scanner_triage" not in result["completed_stages"]
    assert result["progress_percent"] < 100


def test_stage_identity_drift_is_rejected() -> None:
    executors = {stage: _executor for stage in COMPREHENSIVE_STAGES}
    executors[COMPREHENSIVE_STAGES[0]] = lambda context: {"status": "complete", "commit_sha": "different"}

    try:
        run_comprehensive_stages(_state(), executors)
    except ValueError as error:
        assert "commit_sha_identity_drift" in str(error)
    else:
        raise AssertionError("identity drift must be rejected")


def test_unauthorized_state_never_executes() -> None:
    state = build_comprehensive_run_state(
        run_id="comprehensive_run_123",
        repository="BoneManTGRM/NICO",
        commit_sha="abc123",
        evidence_ledger_id="ledger_123",
        authorized=False,
    )
    called = []

    def executor(context):
        called.append(context["stage_id"])
        return {"status": "complete"}

    result = run_comprehensive_stages(state, {stage: executor for stage in COMPREHENSIVE_STAGES})
    assert result["status"] == "blocked"
    assert "explicit_authorization_required" in result["blockers"]
    assert called == []
