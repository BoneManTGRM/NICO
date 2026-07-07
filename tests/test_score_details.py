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
    assert result["lowest_sections"][0]["id"] == "b"


def test_attach_score_details_preserves_payload():
    result = attach_score_details({"run_id": "run_1", "sections": []})

    assert result["run_id"] == "run_1"
    assert result["score_details"]["status"] == "unavailable"
