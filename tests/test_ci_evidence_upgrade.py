from pathlib import Path

from nico.hosted_assessment import analyze_ci


def test_nico_ci_workflow_has_frontend_and_docker_evidence():
    workflow = Path(".github/workflows/nico-ci.yml").read_text(encoding="utf-8")
    lower = workflow.lower()

    assert "npm install" in lower
    assert "npm run lint" in lower
    assert "npm run build" in lower
    assert "docker build" in lower


def test_ci_scoring_counts_frontend_and_docker_evidence():
    workflow = Path(".github/workflows/nico-ci.yml").read_text(encoding="utf-8")
    result = analyze_ci(
        {".github/workflows/nico-ci.yml": workflow},
        [],
        [{"conclusion": "success"}],
        None,
    )

    assert result["score"] >= 88
    assert result["findings"] == []
    assert any("test, lint, or build" in item for item in result["evidence"])
    assert any("deployment-related" in item for item in result["evidence"])
