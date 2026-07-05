"""Phase 3 HTML Regression Test (updated)

Ensures all main HTML headings are present, including GitHub Activity.
"""

from pathlib import Path
from nico.assessment import run_assessment


def test_html_contains_all_sections():
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_html_test")
    html_path = Path("/tmp/nico_html_test/assessment_latest.html")
    content = html_path.read_text(encoding="utf-8")

    assert "Maturity" in content
    assert "Resourcing" in content
    assert "Roadmap" in content
    assert "GitHub Activity" in content
    assert "Ranked Recommendations" in content
    assert "Limitations" in content
