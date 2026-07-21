from nico.express_final_truth_repair_v34 import (
    _normalize_terminal_progress,
    _technical_evidence_projection,
)


def test_ordinary_architecture_findings_are_not_double_charged() -> None:
    section = {
        "id": "architecture_debt",
        "findings": [
            "Source-file footprint is large and increases review scope.",
            "At least one function has very high cyclomatic complexity.",
        ],
        "evidence": ["Complexity engine analyzed 1057 source files."],
    }

    projected = _technical_evidence_projection(section)

    assert projected["findings"] == []
    assert section["findings"]


def test_historical_ci_context_is_not_a_current_score_deduction() -> None:
    section = {
        "id": "ci_cd",
        "findings": [
            "Historical workflow reliability includes 15 non-success run(s); review reliability history separately from current release readiness."
        ],
    }

    projected = _technical_evidence_projection(section)

    assert projected["findings"] == []


def test_business_context_limitations_do_not_reduce_technical_health() -> None:
    section = {
        "id": "velocity_complexity",
        "unavailable": [
            "Precise story points, reviewer seniority, project trend history, and client acceptance require human review.",
            "Required runtime artifact is unavailable.",
        ],
    }

    projected = _technical_evidence_projection(section)

    assert projected["unavailable"] == ["Required runtime artifact is unavailable."]


def test_terminal_response_cannot_show_running_truth_gate_and_complete() -> None:
    result = {
        "status": "complete",
        "progress": [
            {"step": "truth_and_review_gates", "status": "running", "message": "Applying gates."},
            {"step": "complete", "status": "complete", "message": "Done."},
        ],
    }

    _normalize_terminal_progress(result)

    assert all(item["status"] == "complete" for item in result["progress"])
    assert result["terminal_state"] == "human_review_pending"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
