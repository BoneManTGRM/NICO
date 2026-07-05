"""Phase 2 Roadmap Tests

Tests roadmap integration.
"""

from nico.assessment import run_assessment

from nico.modules.roadmap import build_roadmap

from pathlib import Path


def test_roadmap_module_works():
    result = {"findings_count": 5}
    road = build_roadmap(result)
    assert road["status"] == "completed"
    assert "phases" in road
    assert "30_days" in road["phases"]
    assert "60_days" in road["phases"]
    assert "90_days" in road["phases"]


def test_assessment_includes_roadmap():
    result = run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_roadmap_test")
    assert "roadmap" in result
    assert "phases" in result["roadmap"]


def test_markdown_and_json_contain_roadmap():
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_roadmap_test")
    md_path = Path("/tmp/nico_roadmap_test/assessment_latest.md")
    json_path = Path("/tmp/nico_roadmap_test/assessment_latest.json")

    md_content = md_path.read_text(encoding="utf-8")
    assert "## Roadmap" in md_content
    assert "30 Days" in md_content
    assert "60 Days" in md_content
    assert "90 Days" in md_content

    json_content = json_path.read_text(encoding="utf-8")
    assert "roadmap" in json_content
