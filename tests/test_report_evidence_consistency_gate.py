from __future__ import annotations

from nico.report_evidence_consistency_gate import apply_report_evidence_consistency_gate


def _section(section_id: str, score: int, *, evidence=None, unavailable=None, findings=None):
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "status": "green" if score >= 80 else "yellow",
        "summary": section_id,
        "evidence": evidence or [],
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def _base_result():
    return {
        "status": "complete",
        "report_run_id": "run-1",
        "maturity_signal": {"level": "Senior", "score": 91},
        "sections": [
            _section("code_audit", 86),
            _section("dependency_health", 90),
            _section("secrets_review", 92),
            _section("static_analysis", 90),
            _section("ci_cd", 95),
            _section(
                "architecture_debt",
                94,
                evidence=["Architecture complexity support: current-run complexity artifact reports 0 analyzed source file(s)."],
            ),
            _section(
                "velocity_complexity",
                90,
                evidence=[
                    "Complexity engine current-run artifact completed: 0 source file(s), 0 LOC, 0 function-like units.",
                    "Verified score lift: dependency/static proof and complexity evidence are bound to this report run.",
                ],
            ),
        ],
    }


def test_zero_measurement_complexity_cannot_support_express_score_lift():
    result = _base_result()
    profile = {
        "source_file_count": 498,
        "analyzed_file_count": 0,
        "total_loc": 0,
        "total_functions": 0,
        "complexity_score": 0,
        "velocity_score": 90,
        "risk_level": "review_required",
    }
    result["complexity_engine"] = profile
    result["complexity_artifact"] = {
        "status": "completed",
        "verified_for_this_report": True,
        "report_run_id": "run-1",
        "profile": profile,
        "summary": {
            "analyzed_file_count": 0,
            "total_loc": 0,
            "total_functions": 0,
            "risk_level": "review_required",
        },
    }

    output = apply_report_evidence_consistency_gate(result)
    sections = {item["id"]: item for item in output["sections"]}

    assert output["complexity_artifact"]["status"] == "unavailable"
    assert output["complexity_artifact"]["verified_for_this_report"] is False
    assert sections["velocity_complexity"]["score"] == 79
    assert sections["velocity_complexity"]["status"] == "yellow"
    assert sections["architecture_debt"]["score"] == 89
    assert not any("artifact completed" in line.lower() for line in sections["velocity_complexity"]["evidence"])
    assert any("unavailable for scoring" in line.lower() for line in sections["velocity_complexity"]["evidence"])
    assert output["final_evidence_score_bridge"]["complexity_profile_attached"] is False
    assert output["report_quality_guards"]["cross_tier_complexity_consistency"]["status"] == "blocked"
    assert output["maturity_signal"]["score"] < 91


def test_positive_same_run_complexity_remains_score_eligible():
    result = _base_result()
    profile = {
        "source_file_count": 46,
        "analyzed_file_count": 46,
        "total_loc": 4801,
        "total_functions": 211,
        "complexity_score": 76,
        "velocity_score": 76,
        "risk_level": "medium",
    }
    result["complexity_engine"] = profile
    result["complexity_artifact"] = {
        "status": "completed",
        "verified_for_this_report": True,
        "report_run_id": "run-1",
        "profile": profile,
        "summary": {
            "analyzed_file_count": 46,
            "total_loc": 4801,
            "total_functions": 211,
            "risk_level": "medium",
        },
    }

    output = apply_report_evidence_consistency_gate(result)
    sections = {item["id"]: item for item in output["sections"]}

    assert output["complexity_artifact"]["status"] == "completed"
    assert sections["velocity_complexity"]["score"] == 90
    assert sections["architecture_debt"]["score"] == 94
    assert output["final_evidence_score_bridge"]["complexity_profile_verified"] is True
    assert output["report_quality_guards"]["cross_tier_complexity_consistency"]["status"] == "verified"


def test_verified_full_history_removes_stale_secret_limitation():
    result = _base_result()
    secret = next(item for item in result["sections"] if item["id"] == "secrets_review")
    secret["unavailable"] = [
        "Sampled current-tree review is not full git-history proof; a dedicated history scanner remains required for a high-confidence clean claim.",
        "Human review remains required before delivery.",
    ]
    result["scanner_worker_artifact"] = {
        "checkout": {"history_depth": "full", "full_history_secret_scan_requested": True},
        "secret_history_scan": {
            "completed_tools": ["gitleaks", "trufflehog"],
            "full_history_verified": True,
        },
        "tools": {
            "gitleaks": {
                "status": "completed",
                "finding_count": 0,
                "verified_for_this_report": True,
                "full_history_covered": True,
            },
            "trufflehog": {
                "status": "completed",
                "finding_count": 0,
                "verified_for_this_report": True,
                "full_history_covered": True,
            },
        },
    }

    output = apply_report_evidence_consistency_gate(result)
    secret = next(item for item in output["sections"] if item["id"] == "secrets_review")

    assert not any("dedicated history scanner remains required" in line.lower() for line in secret["unavailable"])
    assert "Human review remains required before delivery." in secret["unavailable"]
    assert any("limitation reconciled" in line.lower() for line in secret["evidence"])
    assert output["report_quality_guards"]["secret_history_consistency"]["status"] == "verified"
