from copy import deepcopy

import pytest

from nico.comprehensive_four_phase_model_v1 import (
    apply_four_phase_program,
    build_four_phase_program,
    four_phase_markdown,
)


def _canonical(truth: object, *, language: str = "en") -> dict:
    return {
        "identity": {"report_language": language},
        "assessment_state": "review_required",
        "review_package_ready": True,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "human_review_truth": truth,
    }


@pytest.mark.parametrize(
    ("language", "phase_row"),
    [
        ("en", "| 2 | Human Review by Exception | COMPLETE |"),
        ("es-MX", "| 2 | Revisión humana por excepción | COMPLETA |"),
    ],
)
def test_completed_dispositions_and_qc_finish_phase2_without_approval(
    language: str, phase_row: str
) -> None:
    source = _canonical(
        {
            "authorized_human_disposition_pending": 0,
            "authorized_human_disposition_completed": 15,
            "review_ready_for_final_approval": True,
            "final_human_approval_status": "pending",
            "client_delivery_authorization_status": "blocked",
        },
        language=language,
    )
    original = deepcopy(source)
    canonical = apply_four_phase_program(source)
    program = canonical["four_phase_program"]

    assert program["phases"][1]["status"] == "complete"
    assert canonical["assessment"]["four_phase_program"] == program
    assert phase_row in four_phase_markdown(canonical)
    assert program["human_approval_completed"] is False
    assert program["client_delivery_allowed"] is False
    assert program["phases"][3]["status"] == "blocked_pending_authorized_human_approval"
    assert canonical["human_review_completed"] is False
    assert canonical["human_review_required"] is True
    assert canonical["human_review_truth"] == original["human_review_truth"]
    assert source == original


@pytest.mark.parametrize(
    "truth",
    [
        None,
        {},
        {"authorized_human_disposition_pending": 0},
        {"authorized_human_disposition_pending": 0, "review_ready_for_final_approval": False},
        {"authorized_human_disposition_pending": 0, "review_ready_for_final_approval": "true"},
        {"authorized_human_disposition_pending": 0, "review_ready_for_final_approval": 1},
        {"review_ready_for_final_approval": True},
        {"authorized_human_disposition_pending": None, "review_ready_for_final_approval": True},
        {"authorized_human_disposition_pending": False, "review_ready_for_final_approval": True},
        {"authorized_human_disposition_pending": "0", "review_ready_for_final_approval": True},
        {"authorized_human_disposition_pending": 1, "review_ready_for_final_approval": True},
        {"authorized_human_disposition_pending": -1, "review_ready_for_final_approval": True},
    ],
)
def test_incomplete_or_unverified_review_truth_cannot_finish_phase2(truth: object) -> None:
    program = build_four_phase_program(_canonical(truth))
    assert program["phases"][1]["status"] == "ready_pending_human_decision"
    assert program["human_approval_completed"] is False
    assert program["client_delivery_allowed"] is False


def test_prior_completed_human_review_retains_existing_phase2_semantics() -> None:
    canonical = _canonical(None)
    canonical["human_review_completed"] = True
    program = build_four_phase_program(canonical)
    assert program["phases"][1]["status"] == "complete"
    assert program["human_approval_completed"] is True
    assert program["client_delivery_allowed"] is False
    assert program["phases"][3]["status"] == "blocked_pending_authorized_human_approval"
