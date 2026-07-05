"""Phase 2 Maturity Tests

Tests maturity integration and HTML sections.
"""

from nico.assessment import run_assessment

from pathlib import Path


def test_maturity_exists_and_runs():
    from nico.modules.maturity import assess_maturity
    result = {"findings_count": 3}
    mat = assess_maturity(result)
    assert mat["status"] == "completed"
    assert mat["semaphore"] in ["Green", "Yellow", "Red"]
    assert 0 <= mat["score"] <= 100


def test_assessment_includes_maturity():
    result = run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_maturity_test")
    assert "maturity" in result
    assert result["maturity"]["semaphore"] in ["Green", "Yellow", "Red"]


def test_html_contains_sections():
    # Run assessment first
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_maturity_test")
    html_path = Path("/tmp/nico_maturity_test/assessment_latest.html")
    content = html_path.read_text(encoding="utf-8")
    assert "Maturity" in content
    assert "Dependency Audit" in content
    assert "CI/CD Audit" in content
    assert "Architecture" in content
