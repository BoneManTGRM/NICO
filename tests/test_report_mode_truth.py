from __future__ import annotations

from nico.report_path_truth import apply_report_path_truth


def test_full_report_path_forces_full_mode_everywhere() -> None:
    result = {
        "mode": "express",
        "assessment_mode": "express",
        "reports": {"markdown": "# Draft", "html": "<html><body>Draft</body></html>"},
        "assessment": {"mode": "express", "assessment_mode": "express"},
        "human_review_required": True,
        "client_ready": False,
    }

    output = apply_report_path_truth(result, "full_run")

    assert output["mode"] == "full"
    assert output["assessment_mode"] == "full"
    assert output["reports"]["assessment_mode"] == "full"
    assert output["assessment"]["mode"] == "full"
    assert output["assessment"]["assessment_mode"] == "full"
    assert output["assessment_mode_conflict"] == {
        "detected": True,
        "expected": "full",
        "observed": ["express"],
        "message": "Conflicting assessment-mode metadata was corrected to the endpoint's canonical mode and requires human review.",
    }
    assert output["human_review_required"] is True
    assert output["client_ready"] is False


def test_express_report_path_forces_express_mode_without_false_conflict() -> None:
    result = {
        "mode": "express",
        "assessment_mode": "express",
        "reports": {},
        "assessment": {},
    }

    output = apply_report_path_truth(result, "express")

    assert output["mode"] == "express"
    assert output["assessment_mode"] == "express"
    assert output["reports"]["assessment_mode"] == "express"
    assert output["assessment"]["assessment_mode"] == "express"
    assert "assessment_mode_conflict" not in output


def test_full_path_conflict_and_mode_conflict_remain_separate_evidence() -> None:
    output = apply_report_path_truth(
        {
            "report_path": "express",
            "mode": "mid",
            "reports": {},
            "assessment": {},
            "client_ready": True,
            "human_review_required": False,
        },
        "full_run",
    )

    assert output["report_path_conflict"]["observed"] == ["express"]
    assert output["assessment_mode_conflict"]["observed"] == ["mid"]
    assert output["client_ready"] is False
    assert output["human_review_required"] is True
