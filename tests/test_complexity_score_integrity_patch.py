from __future__ import annotations

from nico import complexity_engine
from nico import evidence_status
from nico import hosted_report_regression_patch
from nico import report_evidence_consistency_runtime
from nico.complexity_score_integrity_patch import (
    _calibrated_score_profile,
    install_complexity_score_integrity_patch,
    select_strongest_complexity_profile,
)


def _section(section_id: str, score: int, *, stale: bool = False) -> dict:
    stale_detail = "Complexity evidence unavailable for scoring: analyzed_files=0, LOC=0, function_units=0, risk=review_required."
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "status": "yellow" if score >= 55 else "red",
        "summary": "The same-run analyzer did not produce valid measurements." if stale else "Measured evidence.",
        "evidence": [stale_detail] if stale else [],
        "findings": [],
        "unavailable": [
            "Maintainability and complexity conclusions remain unavailable until a valid same-run analyzer artifact is attached."
        ] if stale else [],
    }


def test_valid_scanner_summary_supersedes_stale_zero_placeholder() -> None:
    result = {
        "status": "complete",
        "run_id": "express_run_123",
        "report_run_id": "express_run_123",
        "repository": "BoneManTGRM/NICO",
        "sections": [
            _section("architecture_debt", 45, stale=True),
            _section("velocity_complexity", 79, stale=True),
        ],
        "complexity_engine": {
            "status": "attached",
            "source": "current-run scanner artifact evidence",
            "risk_level": "review_required",
        },
        "complexity_artifact": {
            "status": "unavailable",
            "verified_for_this_report": False,
            "report_run_id": "express_run_123",
            "profile": {
                "source": "current-run scanner artifact evidence",
                "risk_level": "review_required",
            },
        },
        "complexity_engine_summary": {
            "artifact_schema": "nico.complexity_attachment.v1",
            "status": "completed",
            "current_run": True,
            "verified_for_this_report": True,
            "source_file_count": 692,
            "total_loc": 92091,
            "total_functions": 5161,
            "call_graph_edge_count": 12500,
            "max_file_cyclomatic_complexity": 246,
            "max_function_cyclomatic_complexity": 18,
            "complexity_score": 76,
            "architecture_score": 80,
            "velocity_score": 84,
            "risk_level": "medium",
            "hotspot_count": 12,
            "top_hotspots": [],
        },
    }
    status = {
        "complexity_tools": {
            "call_graph": {"status": "completed_clean"},
            "cyclomatic_complexity": {"status": "completed_clean"},
            "hotspot_churn": {"status": "completed_clean"},
        }
    }

    evidence_status._apply_complexity_language(result, status)
    report_evidence_consistency_runtime.apply_report_evidence_consistency_gate(result)

    profile, origin = select_strongest_complexity_profile(result)
    assert origin in {"result.complexity_engine", "complexity_artifact.profile", "result.complexity_engine_summary"}
    assert profile["analyzed_file_count"] == 692
    assert profile["total_loc"] == 92091
    assert result["complexity_artifact"]["status"] == "completed"
    assert result["complexity_artifact"]["verified_for_this_report"] is True
    guard = result["report_quality_guards"]["cross_tier_complexity_consistency"]
    assert guard["status"] == "verified"
    assert guard["analyzed_file_count"] == 692
    for section in result["sections"]:
        combined = " ".join(str(item) for key in ("evidence", "findings", "unavailable") for item in section.get(key, []))
        assert "analyzed_files=0" not in combined
        assert "valid same-run analyzer artifact" not in combined


def test_repository_size_alone_does_not_create_technical_debt_penalty() -> None:
    files = [
        {
            "path": f"nico/module_{index}.py",
            "loc": 260,
            "function_count": 20,
            "cyclomatic_complexity": 22,
            "max_function_complexity": 3,
            "churn": 20,
            "primary_owner": "owner@example.com",
            "owner_concentration": 0.65,
        }
        for index in range(300)
    ]
    churn = {item["path"]: item["churn"] for item in files}
    concentration = {item["path"]: item["owner_concentration"] for item in files}

    score, risk, findings = _calibrated_score_profile(files, churn, concentration, 30)

    assert score >= 90
    assert risk == "low"
    assert any("size is not scored as technical debt" in item for item in findings)


def test_measured_function_risk_and_churn_overlap_reduce_score() -> None:
    files = []
    for index in range(14):
        files.append(
            {
                "path": f"nico/hot_{index}.py",
                "loc": 700,
                "function_count": 10,
                "cyclomatic_complexity": 150,
                "max_function_complexity": 30,
                "churn": 800,
                "primary_owner": "owner@example.com",
                "owner_concentration": 1.0,
            }
        )
    churn = {item["path"]: item["churn"] for item in files}
    concentration = {item["path"]: item["owner_concentration"] for item in files}

    score, risk, findings = _calibrated_score_profile(files, churn, concentration, 20)

    assert score < 82
    assert risk in {"medium", "high"}
    assert any("Function-level complexity risk" in item for item in findings)
    assert any("Complexity and high churn overlap" in item for item in findings)


def test_calibrated_profile_reports_function_risk_density(tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "nico").mkdir(parents=True)
    (repo / "nico" / "app.py").write_text(
        "def alpha(value):\n"
        "    if value:\n"
        "        return value\n"
        "    return None\n",
        encoding="utf-8",
    )

    profile = complexity_engine.build_complexity_profile(repo)

    assert profile["scoring_model"] == "function_risk_density_v3"
    assert profile["max_function_cyclomatic_complexity"] >= 2
    assert profile["complexity_density_per_100_loc"] > 0
    assert profile["architecture_score"] >= profile["complexity_score"]
    assert profile["velocity_score"] >= profile["complexity_score"]
    assert "size and development activity" in profile["guardrail"]


def test_ci_release_selection_prefers_conclusive_default_branch_run() -> None:
    runs = [
        {
            "name": "NICO CI",
            "status": "in_progress",
            "conclusion": None,
            "head_branch": "agent/temporary-verification",
            "event": "pull_request",
        },
        {
            "name": "NICO CI",
            "status": "completed",
            "conclusion": "failure",
            "head_branch": "agent/feature",
            "event": "pull_request",
        },
        {
            "name": "NICO CI",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "event": "push",
        },
    ]

    latest = hosted_report_regression_patch._latest_runs_by_name(runs)

    assert latest["NICO CI"]["conclusion"] == "success"
    assert latest["NICO CI"]["head_branch"] == "main"


def test_installation_is_idempotent() -> None:
    first = install_complexity_score_integrity_patch()
    second = install_complexity_score_integrity_patch()

    assert first["status"] == "installed"
    assert second["status"] == "installed"
    assert first["function_risk_density_scoring"] is True
    assert second["placeholder_profile_overwrite_blocked"] is True
