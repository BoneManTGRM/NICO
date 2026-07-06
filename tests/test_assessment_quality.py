from nico.assessment_quality import polish_express_result


def test_metadata_limited_sections_are_degraded_not_red():
    result = {
        "status": "complete",
        "executive_summary": "Assessment complete.",
        "sections": [
            {
                "id": "code_audit",
                "score": 36,
                "status": "red",
                "evidence": ["No recent pull-request evidence was found; direct-to-main work may reduce review traceability."],
                "findings": ["No recent pull-request evidence was found; direct-to-main work may reduce review traceability."],
                "unavailable": ["Commit activity unavailable: GitHub returned 403: API rate limit exceeded"],
            },
            {
                "id": "ci_cd",
                "score": 20,
                "status": "red",
                "evidence": ["No GitHub Actions workflow files were available for analysis."],
                "findings": ["No CI/CD workflow files were found through GitHub contents access."],
                "unavailable": ["Workflow run history unavailable: GitHub returned 403: API rate limit exceeded"],
            },
            {
                "id": "architecture_debt",
                "score": 76,
                "status": "green",
                "evidence": ["Repository root contains .github/."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "score": 51,
                "status": "yellow",
                "evidence": ["Commit velocity: 0 commits over 180 days (0.0/week).", "Pull request traceability ratio: 0 PRs / 0 commits = 0."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "dependency_health",
                "score": 30,
                "status": "red",
                "evidence": ["OSV returned 2 records for streamlit.", "OSV returned 2 records for streamlit."],
                "findings": ["OSV returned 2 records for streamlit.", "OSV returned 2 records for streamlit."],
                "unavailable": [],
            },
        ],
    }

    polished = polish_express_result(result)
    code = next(item for item in polished["sections"] if item["id"] == "code_audit")
    ci = next(item for item in polished["sections"] if item["id"] == "ci_cd")
    velocity = next(item for item in polished["sections"] if item["id"] == "velocity_complexity")
    deps = next(item for item in polished["sections"] if item["id"] == "dependency_health")

    assert polished["assessment_quality"] == "degraded_metadata"
    assert code["status"] == "yellow"
    assert code["score"] >= 55
    assert not any("No recent pull-request evidence" in note for note in code["findings"])
    assert ci["status"] == "yellow"
    assert ci["score"] >= 50
    assert not any("No CI/CD workflow files" in note for note in ci["findings"])
    assert velocity["score"] >= 55
    assert not any("0 commits over" in note for note in velocity["evidence"])
    assert deps["evidence"].count("OSV returned 2 records for streamlit.") == 1
