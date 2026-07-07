from nico.final_report_consistency import finalize_express_result_consistency


def test_finalize_express_result_attaches_score_details():
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "sections": [
                {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 72, "status": "yellow", "evidence": ["dependency evidence"], "findings": [], "unavailable": ["audit evidence missing"]},
                {"id": "ci_cd", "label": "CI/CD Analysis", "score": 74, "status": "yellow", "evidence": ["ci evidence"], "findings": [], "unavailable": ["build evidence missing"]},
                {"id": "static_analysis", "label": "Static Analysis", "score": 90, "status": "green", "evidence": ["static evidence"], "findings": [], "unavailable": []},
            ],
            "reports": {},
        }
    )

    assert result["score_details"]["status"] == "ok"
    assert result["score_details"]["section_count"] == 3
    assert result["score_details"]["lowest_sections"][0]["id"] == "dependency_health"
    assert result["score_source_of_truth"]["field"] == "maturity_signal"
