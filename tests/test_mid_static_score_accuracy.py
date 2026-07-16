from __future__ import annotations

from nico import full_assessment_scorecard as scorecard
from nico.mid_static_score_accuracy import (
    MID_STATIC_SCORE_ACCURACY_VERSION,
    install_mid_static_score_accuracy,
)


def _repo(risks: int = 0) -> dict:
    return {
        "code_signal_evidence": {"risk_pattern_hits": risks},
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
        "tools_run": run or [],
        "tools_requested": requested or [],
        "failed_tools": failed or [],
        "timed_out_tools": timed_out or [],
        "unavailable_tools": unavailable or [],
    }


def test_typescript_completion_receives_bounded_static_analysis_credit() -> None:
    installed = install_mid_static_score_accuracy()
    assert installed["version"] == MID_STATIC_SCORE_ACCURACY_VERSION

    section = scorecard._static_section(
        _repo(),
        _scanner(
            run=["bandit", "typescript"],
            requested=["bandit", "typescript"],
        ),
    )

    # Legacy scoring credited Bandit but ignored TypeScript: 48 + 10 + 10 = 68.
    # The compiler evidence now receives the same bounded per-tool credit.
    assert section["score"] == 78
    assert section["status"] == "yellow"
    breakdown = section["score_evidence_breakdown"]
    assert breakdown["pre_typescript_score"] == 68
    assert breakdown["typescript_state"] == "completed"
    assert breakdown["typescript_score_adjustment"] == 10
    assert breakdown["post_typescript_score"] == 78
    assert breakdown["typescript_execution_treated_as_clean"] is False
    assert breakdown["typescript_accuracy_applied"] is True
    assert breakdown["version"] == MID_STATIC_SCORE_ACCURACY_VERSION
    assert any("TypeScript compiler static-analysis state=completed" in item for item in section["evidence"])


def test_typescript_failure_reduces_score_and_preserves_incomplete_conclusion() -> None:
    install_mid_static_score_accuracy()
    section = scorecard._static_section(
        _repo(),
        _scanner(
            run=["bandit"],
            requested=["bandit", "typescript"],
            failed=["typescript"],
        ),
    )

    assert section["score"] == 56
    assert section["score_evidence_breakdown"]["typescript_score_adjustment"] == -12
    assert section["score_evidence_breakdown"]["typescript_state"] == "failed"
    assert any("TypeScript static-analysis execution failed" in item for item in section["findings"])


def test_typescript_unavailable_is_not_treated_as_clean_or_successful() -> None:
    install_mid_static_score_accuracy()
    section = scorecard._static_section(
        _repo(risks=1),
        _scanner(
            run=["bandit"],
            requested=["bandit", "typescript"],
            unavailable=["typescript"],
        ),
    )

    breakdown = section["score_evidence_breakdown"]
    assert breakdown["typescript_state"] == "unavailable"
    assert breakdown["typescript_score_adjustment"] == -5
    assert breakdown["typescript_execution_treated_as_clean"] is False
    assert section["score"] < 60
    assert section["findings"]
    assert not any("clean" in item.lower() for item in section["verified_claims"])


def test_installation_is_idempotent() -> None:
    first = install_mid_static_score_accuracy()
    second = install_mid_static_score_accuracy()

    assert first["version"] == MID_STATIC_SCORE_ACCURACY_VERSION
    assert second == {"status": "already_installed", "version": MID_STATIC_SCORE_ACCURACY_VERSION}
