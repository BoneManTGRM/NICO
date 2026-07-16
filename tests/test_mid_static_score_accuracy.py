from __future__ import annotations

from copy import deepcopy

from nico.mid_assessment_handlers import mid_assessment_handlers
from nico.mid_static_score_accuracy import (
    MID_STATIC_SCORE_ACCURACY_VERSION,
    apply_typescript_static_evidence,
    mid_scoring_handler,
)


def _assessment(static_score: int = 68) -> dict:
    scores = {
        "code_audit": 60,
        "dependency_health": 72,
        "secrets_review": 80,
        "static_analysis": static_score,
        "ci_cd": 95,
        "architecture_debt": 85,
        "velocity_complexity": 76,
    }
    return {
        "status": "draft",
        "maturity_signal": {"score": 76, "level": "Mid"},
        "scorecard": {"technical_score": 76},
        "sections": [
            {
                "id": section_id,
                "label": section_id.replace("_", " ").title(),
                "score": score,
                "status": "green" if score >= 80 else "yellow" if score >= 55 else "red",
                "evidence": [f"Evidence for {section_id}."],
                "verified_claims": [f"Evidence for {section_id}."],
                "findings": [],
                "unavailable": [],
            }
            for section_id, score in scores.items()
        ],
    }


def _scanner(
    *,
    run: list[str] | None = None,
    requested: list[str] | None = None,
    failed: list[str] | None = None,
    timed_out: list[str] | None = None,
    unavailable: list[str] | None = None,
) -> dict:
    return {
        "status": "attached",
        "run_id": "midrun_static_accuracy",
        "tools_run": run or [],
        "tools_requested": requested or [],
        "failed_tools": failed or [],
        "timed_out_tools": timed_out or [],
        "unavailable_tools": unavailable or [],
    }


def _static(adjusted: dict) -> dict:
    return next(item for item in adjusted["sections"] if item["id"] == "static_analysis")


def test_typescript_completion_receives_bounded_mid_static_analysis_credit() -> None:
    adjusted = apply_typescript_static_evidence(
        _assessment(68),
        _scanner(run=["bandit", "typescript"], requested=["bandit", "typescript"]),
    )
    section = _static(adjusted)

    assert section["score"] == 78
    assert section["status"] == "yellow"
    breakdown = section["score_evidence_breakdown"]
    assert breakdown["pre_typescript_score"] == 68
    assert breakdown["typescript_state"] == "completed"
    assert breakdown["typescript_score_adjustment"] == 10
    assert breakdown["post_typescript_score"] == 78
    assert breakdown["typescript_execution_treated_as_clean"] is False
    assert breakdown["version"] == MID_STATIC_SCORE_ACCURACY_VERSION
    assert any("TypeScript compiler static-analysis state=completed" in item for item in section["evidence"])
    assert adjusted["mid_static_score_accuracy"]["express_score_changed"] is False
    assert adjusted["mid_static_score_accuracy"]["full_score_changed"] is False


def test_typescript_failure_reduces_mid_score_and_preserves_incomplete_conclusion() -> None:
    adjusted = apply_typescript_static_evidence(
        _assessment(68),
        _scanner(run=["bandit"], requested=["bandit", "typescript"], failed=["typescript"]),
    )
    section = _static(adjusted)

    assert section["score"] == 56
    assert section["score_evidence_breakdown"]["typescript_score_adjustment"] == -12
    assert section["score_evidence_breakdown"]["typescript_state"] == "failed"
    assert any("TypeScript static-analysis execution failed" in item for item in section["findings"])


def test_typescript_unavailable_is_not_treated_as_clean_or_successful() -> None:
    adjusted = apply_typescript_static_evidence(
        _assessment(58),
        _scanner(run=["bandit"], requested=["bandit", "typescript"], unavailable=["typescript"]),
    )
    section = _static(adjusted)
    breakdown = section["score_evidence_breakdown"]

    assert section["score"] == 53
    assert breakdown["typescript_state"] == "unavailable"
    assert breakdown["typescript_score_adjustment"] == -5
    assert breakdown["typescript_execution_treated_as_clean"] is False
    assert section["findings"]
    assert not any("clean result" in item.lower() for item in section["verified_claims"])


def test_mid_static_accuracy_is_idempotent_for_same_assessment_and_scanner_state() -> None:
    scanner = _scanner(run=["bandit", "typescript"], requested=["bandit", "typescript"])
    once = apply_typescript_static_evidence(_assessment(68), scanner)
    twice = apply_typescript_static_evidence(once, scanner)

    assert _static(once)["score"] == 78
    assert _static(twice)["score"] == 78
    assert twice == once


def test_mid_pipeline_uses_mid_only_scoring_handler() -> None:
    handlers = mid_assessment_handlers()

    assert handlers["scoring"] is mid_scoring_handler


def test_mid_scoring_handler_applies_accuracy_after_shared_scorecard(monkeypatch) -> None:
    base = {
        "status": "complete",
        "message": "Shared scorecard complete.",
        "assessment": _assessment(68),
        "evidence": {"technical_score": 76},
    }

    monkeypatch.setattr(
        "nico.mid_static_score_accuracy.full_assessment_scoring_handler",
        lambda context, outputs: deepcopy(base),
    )
    outputs = {
        "evidence_attachment": {
            "scanner_evidence": _scanner(
                run=["bandit", "typescript"],
                requested=["bandit", "typescript"],
            )
        }
    }
    result = mid_scoring_handler({"run_id": "midrun_static_accuracy"}, outputs)

    assert result["status"] == "complete"
    assert _static(result["assessment"])["score"] == 78
    assert result["evidence"]["technical_score"] == result["assessment"]["maturity_signal"]["score"]
    assert result["evidence"]["mid_static_score_accuracy"]["typescript_state"] == "completed"
