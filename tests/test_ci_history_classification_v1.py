from nico.ci_history_classification_v1 import (
    classify_workflow_history,
    classify_workflow_run,
)


def _run(run_id: int, conclusion: str, **extra):
    payload = {
        "id": run_id,
        "name": "NICO CI",
        "status": "completed",
        "conclusion": conclusion,
        "event": "push",
        "head_sha": "a" * 40,
        "actor": {"login": "octocat"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:01:00Z",
    }
    payload.update(extra)
    return payload


def test_genuine_failure_affects_rate() -> None:
    result = classify_workflow_run(_run(1, "failure"))
    assert result["category"] == "genuine_failure"
    assert result["affects_historical_failure_rate"] is True


def test_cancellation_does_not_count_as_failure() -> None:
    result = classify_workflow_run(_run(2, "cancelled", reason="superseded by newer run"))
    assert result["category"] == "superseded_cancellation"
    assert result["affects_historical_failure_rate"] is False


def test_missing_terminal_conclusion_fails_closed() -> None:
    result = classify_workflow_run(_run(3, ""))
    assert result["category"] == "unknown_review_required"
    assert result["review_required"] is True
    assert "completed_without_conclusion" in result["metadata_blockers"]


def test_history_separates_current_health() -> None:
    summary = classify_workflow_history(
        [_run(1, "success"), _run(2, "failure"), _run(3, "cancelled")],
        current_required_checks={"NICO CI": "success", "CodeQL": "success"},
    )
    assert summary["historical_reliability"]["genuine_failure_rate"] == 0.5
    assert summary["current_branch_health"]["green"] is True
    assert summary["cancellations_counted_as_failures"] is False


def test_infrastructure_fault_is_separate() -> None:
    result = classify_workflow_run(_run(4, "failure", reason="hosted runner service unavailable"))
    assert result["category"] == "infrastructure_fault"
    assert result["affects_historical_failure_rate"] is False
