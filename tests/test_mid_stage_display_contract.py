from __future__ import annotations

from pathlib import Path

from nico.mid_stage_truth_patch import normalize_mid_stage_truth


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_INIT = ROOT / "nico" / "__init__.py"
MID_API = ROOT / "nico" / "mid_assessment_api.py"


def test_mid_planned_artifacts_do_not_appear_skipped_by_user_request() -> None:
    result = {
        "status": "running",
        "report_generation_status": "mid_report_generation_pending",
        "approval_request_status": "pending",
        "progress": [
            {
                "step": "scoring",
                "status": "complete",
                "message": "Full Assessment multi-section scorecard was generated from attached same-run repository and scanner evidence.",
                "evidence": {"score": 71},
            },
            {
                "step": "reports",
                "status": "skipped",
                "message": "Report generation was skipped by request.",
                "evidence": {},
            },
            {
                "step": "approval_request",
                "status": "skipped",
                "message": "Final review request was skipped by request.",
                "evidence": {},
            },
        ],
    }

    output = normalize_mid_stage_truth(result)
    progress = {item["step"]: item for item in output["progress"]}

    assert progress["scoring"]["status"] == "complete"
    assert progress["scoring"]["message"].startswith("Mid Assessment multi-section scorecard")
    assert progress["reports"]["status"] == "planned"
    assert "Dedicated Mid draft generation is planned" in progress["reports"]["message"]
    assert progress["approval_request"]["status"] == "planned"
    assert "Dedicated Mid human-review request is planned" in progress["approval_request"]["message"]
    assert "skipped by request" not in str(output).lower()
    assert output["mid_artifact_execution_contract"]["generic_full_report_handler_enabled"] is False
    assert output["mid_artifact_execution_contract"]["dedicated_mid_report_enabled"] is True


def test_terminal_mid_report_and_review_states_are_not_downgraded_to_planned() -> None:
    result = {
        "status": "blocked",
        "report_generation_status": "blocked",
        "approval_request_status": "not_started",
        "progress": [
            {"step": "reports", "status": "blocked", "message": "Quality gate blocked the draft.", "evidence": {}},
            {"step": "approval_request", "status": "not_started", "message": "Draft unavailable.", "evidence": {}},
        ],
    }

    output = normalize_mid_stage_truth(result)
    progress = {item["step"]: item for item in output["progress"]}

    assert progress["reports"]["status"] == "blocked"
    assert progress["reports"]["message"] == "Quality gate blocked the draft."
    assert progress["approval_request"]["status"] == "not_started"
    assert progress["approval_request"]["message"] == "Draft unavailable."


def test_mid_keeps_generic_full_artifact_handlers_disabled_and_installs_truth_projection() -> None:
    api = MID_API.read_text(encoding="utf-8")
    package = PACKAGE_INIT.read_text(encoding="utf-8")

    assert '"build_reports": False' in api
    assert '"create_final_review_request": False' in api
    assert "install_mid_stage_truth_patch" in package
    assert "install_mid_report_section_boundary_patch" in package
