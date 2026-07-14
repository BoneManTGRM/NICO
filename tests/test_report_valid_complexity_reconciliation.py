from __future__ import annotations

from copy import deepcopy

from nico.report_evidence_consistency_runtime import apply_report_evidence_consistency_gate
from nico.report_valid_complexity_reconciliation import BOUNDED_SCOPE_LIMITATION


def _section(section_id: str, score: int, summary: str) -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "status": "green" if score >= 80 else "yellow",
        "summary": summary,
        "evidence": [],
        "findings": [],
        "unavailable": [],
    }


def _result(profile: dict, *, velocity_score: int = 79, architecture_score: int = 89) -> dict:
    result = {
        "status": "complete",
        "report_run_id": "run-complexity-reconcile",
        "maturity_signal": {"level": "Senior", "score": 86, "summary": "Existing final maturity."},
        "human_review_required": True,
        "client_ready": False,
        "sections": [
            _section("code_audit", 86, "Code evidence available."),
            _section(
                "architecture_debt",
                architecture_score,
                "Architecture is review-limited because the same-run analyzer did not produce valid measurements.",
            ),
            _section(
                "velocity_complexity",
                velocity_score,
                "Commit and pull-request activity is available, but maintainability and complexity remain review-limited because the same-run analyzer did not produce valid measurements.",
            ),
        ],
        "complexity_engine": profile,
        "complexity_artifact": {
            "status": "completed",
            "verified_for_this_report": True,
            "report_run_id": "run-complexity-reconcile",
            "source": profile.get("source") or "checked_out_repository_complexity",
            "evidence_scope": profile.get("evidence_scope") or "Same-run checked-out repository complexity profile.",
            "profile": profile,
            "summary": {
                "analyzed_file_count": profile["analyzed_file_count"],
                "total_loc": profile["total_loc"],
                "total_functions": profile["total_functions"],
                "risk_level": profile["risk_level"],
            },
        },
    }
    velocity = result["sections"][2]
    velocity["evidence"] = [
        "Complexity evidence unavailable for scoring: analyzed_files=0, LOC=0, function_units=0, risk=review_required.",
        "Commit velocity: 100 commits over 180 days.",
    ]
    velocity["unavailable"] = [
        "Maintainability and complexity conclusions remain unavailable until a valid same-run analyzer artifact is attached.",
        "Precise story-point expectation requires stakeholder context and human review.",
    ]
    velocity["scanner_score_lift"] = {
        "applied": False,
        "blocked_reason": "invalid_or_zero_complexity_evidence",
    }
    architecture = result["sections"][1]
    architecture["evidence"] = [
        "Complexity evidence unavailable for scoring: analyzed_files=0, LOC=0, function_units=0, risk=review_required.",
        "Repository architecture layout is available.",
    ]
    architecture["unavailable"] = [
        "Complexity-dependent architecture and technical-debt conclusions are not verified for this report run.",
        "Runtime behavior still requires human review.",
    ]
    return result


def test_bounded_valid_profile_replaces_obsolete_zero_measurement_wording_without_forcing_green() -> None:
    profile = {
        "source": "github_api_exact_commit_bounded_sample",
        "evidence_scope": "Bounded production-source sample fetched at one exact commit.",
        "source_file_count": 640,
        "analyzed_file_count": 48,
        "total_loc": 15420,
        "total_functions": 612,
        "complexity_score": 78,
        "velocity_score": 78,
        "risk_level": "medium",
    }
    result = _result(profile)
    original_maturity = deepcopy(result["maturity_signal"])

    output = apply_report_evidence_consistency_gate(result)
    sections = {item["id"]: item for item in output["sections"]}
    velocity = sections["velocity_complexity"]
    architecture = sections["architecture_debt"]

    assert velocity["score"] == 79
    assert velocity["status"] == "yellow"
    assert architecture["score"] == 89
    assert architecture["status"] == "green"
    assert "valid exact-commit bounded complexity sample" in velocity["summary"]
    assert "valid exact-commit bounded complexity measurements" in architecture["summary"]
    assert not any("analyzed_files=0" in str(item) for item in velocity["evidence"])
    assert not any("same-run analyzer did not produce valid measurements" in str(item).lower() for item in [velocity["summary"], architecture["summary"]])
    assert any("analyzed_files=48" in str(item) and "source=github_api_exact_commit_bounded_sample" in str(item) for item in velocity["evidence"])
    assert BOUNDED_SCOPE_LIMITATION in velocity["unavailable"]
    assert BOUNDED_SCOPE_LIMITATION in architecture["unavailable"]
    assert "Precise story-point expectation requires stakeholder context and human review." in velocity["unavailable"]
    assert "Runtime behavior still requires human review." in architecture["unavailable"]
    assert velocity["scanner_score_lift"]["applied"] is False
    assert "blocked_reason" not in velocity["scanner_score_lift"]
    assert velocity["scanner_score_lift"]["complexity_evidence_reconciled"] is True
    assert output["maturity_signal"] == original_maturity
    assert output["human_review_required"] is True
    assert output["client_ready"] is False

    guard = output["report_quality_guards"]["verified_complexity_reconciliation"]
    assert guard["status"] == "reconciled"
    assert guard["bounded_sample"] is True
    assert guard["score_changed"] is False
    assert guard["status_changed"] is False
    assert guard["human_review_changed"] is False


def test_checked_out_valid_profile_removes_invalid_state_without_adding_bounded_limitation() -> None:
    profile = {
        "source": "checked_out_repository_complexity",
        "source_file_count": 640,
        "analyzed_file_count": 640,
        "total_loc": 107500,
        "total_functions": 4200,
        "complexity_score": 84,
        "velocity_score": 84,
        "risk_level": "medium",
    }
    result = _result(profile, velocity_score=84, architecture_score=86)

    output = apply_report_evidence_consistency_gate(result)
    sections = {item["id"]: item for item in output["sections"]}
    velocity = sections["velocity_complexity"]
    architecture = sections["architecture_debt"]

    assert velocity["score"] == 84
    assert velocity["status"] == "green"
    assert architecture["score"] == 86
    assert architecture["status"] == "green"
    assert "valid same-run checked-out repository measurements" in velocity["summary"]
    assert "valid same-run checked-out repository complexity measurements" in architecture["summary"]
    assert BOUNDED_SCOPE_LIMITATION not in velocity["unavailable"]
    assert BOUNDED_SCOPE_LIMITATION not in architecture["unavailable"]
    assert output["report_quality_guards"]["verified_complexity_reconciliation"]["bounded_sample"] is False


def test_reconciliation_is_idempotent_and_does_not_duplicate_valid_evidence() -> None:
    profile = {
        "source": "github_api_exact_commit_bounded_sample",
        "source_file_count": 20,
        "analyzed_file_count": 20,
        "total_loc": 1500,
        "total_functions": 80,
        "complexity_score": 88,
        "velocity_score": 88,
        "risk_level": "low",
    }
    result = _result(profile, velocity_score=88, architecture_score=90)

    first = apply_report_evidence_consistency_gate(result)
    second = apply_report_evidence_consistency_gate(first)
    velocity = next(item for item in second["sections"] if item["id"] == "velocity_complexity")
    architecture = next(item for item in second["sections"] if item["id"] == "architecture_debt")

    assert sum("Complexity evidence verified for this report run" in str(item) for item in velocity["evidence"]) == 1
    assert sum(item == BOUNDED_SCOPE_LIMITATION for item in velocity["unavailable"]) == 1
    assert sum(item == BOUNDED_SCOPE_LIMITATION for item in architecture["unavailable"]) == 1


def test_invalid_profile_keeps_fail_closed_zero_measurement_state() -> None:
    profile = {
        "source": "github_api_exact_commit_bounded_sample",
        "source_file_count": 640,
        "analyzed_file_count": 0,
        "total_loc": 0,
        "total_functions": 0,
        "complexity_score": 0,
        "velocity_score": 90,
        "risk_level": "review_required",
    }
    result = _result(profile, velocity_score=90, architecture_score=94)

    output = apply_report_evidence_consistency_gate(result)
    sections = {item["id"]: item for item in output["sections"]}

    assert sections["velocity_complexity"]["score"] == 79
    assert sections["velocity_complexity"]["status"] == "yellow"
    assert any("unavailable for scoring" in str(item).lower() for item in sections["velocity_complexity"]["evidence"])
    assert "verified_complexity_reconciliation" not in output["report_quality_guards"]
    assert output["human_review_required"] is True
    assert output["client_ready"] is False
