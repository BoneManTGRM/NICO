from nico.comprehensive_capability_registry import CAPABILITY_REGISTRY
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_stage_adapter import (
    bind_capability_executors,
    build_comprehensive_run_state,
    run_comprehensive_stages,
)


def _capability_executor(context: dict) -> dict:
    return {
        "status": "complete",
        "capability_seen": context["capability"],
        "run_id": context["run_id"],
        "repository": context["repository"],
        "commit_sha": context["commit_sha"],
        "evidence_ledger_id": context["evidence_ledger_id"],
    }


def _state() -> dict:
    return build_comprehensive_run_state(
        run_id="comprun_123",
        repository="BoneManTGRM/NICO",
        commit_sha="abc123",
        evidence_ledger_id="ledger_123",
        authorized=True,
    )


def test_registry_binds_every_stage_from_capability_implementations() -> None:
    capability_executors = {
        item["capability"]: _capability_executor
        for item in CAPABILITY_REGISTRY.values()
    }
    stage_executors = bind_capability_executors(capability_executors)

    assert list(stage_executors) == list(COMPREHENSIVE_STAGES)

    result = run_comprehensive_stages(_state(), stage_executors)
    assert result["status"] == "review_required"
    assert result["progress_percent"] == 100.0
    assert result["completed_stages"] == list(COMPREHENSIVE_STAGES)
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    for stage_id, stage_result in result["stage_results"].items():
        assert stage_result["capability_seen"] == CAPABILITY_REGISTRY[stage_id]["capability"]


def test_missing_capability_blocks_at_first_unbound_stage() -> None:
    capability_executors = {
        item["capability"]: _capability_executor
        for stage_id, item in CAPABILITY_REGISTRY.items()
        if stage_id != "functional_qa"
    }
    stage_executors = bind_capability_executors(capability_executors)

    result = run_comprehensive_stages(_state(), stage_executors)
    assert result["status"] == "blocked"
    assert result["current_stage"] == "functional_qa"
    assert "missing_executor:functional_qa" in result["blockers"]
    assert "functional_qa" not in result["completed_stages"]


def test_capability_receives_identity_and_prior_stage_evidence() -> None:
    calls: list[dict] = []

    def recorder(context: dict) -> dict:
        calls.append(context)
        return _capability_executor(context)

    capability_executors = {
        item["capability"]: recorder
        for item in CAPABILITY_REGISTRY.values()
    }
    result = run_comprehensive_stages(
        _state(),
        bind_capability_executors(capability_executors),
        stop_after=COMPREHENSIVE_STAGES[1],
    )

    assert result["status"] == "paused"
    assert calls[0]["prior_stage_results"] == {}
    assert list(calls[1]["prior_stage_results"]) == [COMPREHENSIVE_STAGES[0]]
    assert calls[1]["run_id"] == "comprun_123"
    assert calls[1]["commit_sha"] == "abc123"
    assert calls[1]["evidence_ledger_id"] == "ledger_123"


def test_non_dictionary_capability_result_is_rejected() -> None:
    def invalid_result(_: dict):
        return "complete"

    first_capability = CAPABILITY_REGISTRY[COMPREHENSIVE_STAGES[0]]["capability"]
    executors = bind_capability_executors({first_capability: invalid_result})

    try:
        run_comprehensive_stages(_state(), executors)
    except TypeError as error:
        assert str(error) == f"capability_executor_must_return_dict:{first_capability}"
    else:
        raise AssertionError("Expected invalid capability result to be rejected")
