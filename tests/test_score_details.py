from nico.score_details import attach_score_details, build_score_details


def test_score_details_averages_sections_and_lists_lowest():
    result = build_score_details(
        {
            "sections": [
                {"id": "a", "score": 90, "status": "green", "evidence": ["x"]},
                {"id": "b", "score": 70, "status": "yellow", "unavailable": ["y"]},
            ]
        }
    )

    assert result["score"] == 80
    assert result["section_count"] == 2
    assert result["scored_section_count"] == 2
    assert result["display_section_count"] == 2
    assert result["lowest_sections"][0]["id"] == "b"


def test_score_details_excludes_supplemental_sections_from_average():
    result = build_score_details(
        {
            "sections": [
                {"id": "core", "score": 90, "status": "green"},
                {"id": "scanner_worker_evidence", "score": 25, "status": "gray", "supplemental": True, "scoring_weight": 0},
            ]
        }
    )

    assert result["score"] == 90
    assert result["section_count"] == 2
    assert result["scored_section_count"] == 1
    assert result["display_section_count"] == 2
    assert result["supplemental_section_count"] == 1
    assert result["lowest_sections"] == [{
        "id": "core",
        "label": "core",
        "score": 90,
        "status": "green",
        "diagnostic_status": None,
        "confidence": None,
        "supplemental": False,
        "scoring_weight": 1,
        "included_in_maturity_score": True,
        "evidence_count": 0,
        "finding_count": 0,
        "unavailable_count": 0,
        "missing_required_sources": [],
    }]
    assert result["supplemental_sections"][0]["id"] == "scanner_worker_evidence"
    assert result["supplemental_sections"][0]["included_in_maturity_score"] is False


def test_attach_score_details_preserves_payload():
    result = attach_score_details({"run_id": "run_1", "sections": []})

    assert result["run_id"] == "run_1"
    assert result["score_details"]["status"] == "unavailable"
