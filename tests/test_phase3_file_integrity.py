"""Phase 3 File Integrity Regression Test

Guards against accidental truncation or fragmentation of critical orchestrator files.
"""

import ast
import py_compile
from pathlib import Path

ASSESSMENT = Path("nico/assessment.py")
REPORTING = Path("nico/modules/reporting.py")


def test_assessment_has_run_assessment():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def run_assessment(" in content


def test_assessment_has_main():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def main(" in content


def test_assessment_contains_all_key_modules():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "github_token_health" in content
    assert "github_activity" in content
    assert "dependency_audit" in content
    assert "cicd_audit" in content
    assert "architecture_audit" in content
    assert "maturity" in content
    assert "resourcing" in content
    assert "roadmap" in content
    assert "synthesis" in content
    assert "write_assessment_reports" in content
    assert "github_token_env=github_token_env" in content
    assert 'parser.add_argument("--github-token-env"' in content


def test_assessment_file_size_and_start():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 200
    # Must start with shebang or docstring/imports, not indented fragment
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("#!/", "\"\"\"", "import ", "from ")) for line in first_lines)


def test_reporting_has_write_assessment_reports():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def write_assessment_reports(" in content


def test_reporting_writes_all_output_files():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "assessment_latest.json" in content
    assert "assessment_latest.md" in content
    assert "assessment_latest.html" in content
    assert "evidence_manifest.json" in content


def test_reporting_contains_all_sections():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "## CI/CD Audit" in content
    assert "## GitHub Activity" in content
    assert "## GitHub Token Health" in content
    assert "## Ranked Recommendations" in content


def test_reporting_contains_details_objects():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "cicd_details" in content
    assert "github_token_health_details" in content
    assert "module_statuses" in content
    assert "ranked_recommendations_with_evidence" in content


def test_reporting_file_size_and_start():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 180
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("\"\"\"", "import ", "from ")) for line in first_lines)


def test_pycompile_assessment():
    py_compile.compile(str(ASSESSMENT), doraise=True)


def test_pycompile_reporting():
    py_compile.compile(str(REPORTING), doraise=True)
