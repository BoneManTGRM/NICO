"""Phase 3 File Integrity Regression Test

Guards against truncation of assessment.py, reporting.py, dependency_audit.py, and synthesis.py.
"""

import py_compile
from pathlib import Path

ASSESSMENT = Path("nico/assessment.py")
REPORTING = Path("nico/modules/reporting.py")
DEPENDENCY = Path("nico/modules/dependency_audit.py")
SYNTHESIS = Path("nico/modules/synthesis.py")


def test_assessment_has_run_assessment():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def run_assessment(" in content


def test_assessment_has_main():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def main(" in content


def test_assessment_contains_key_modules():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "github_token_health" in content
    assert "github_activity" in content
    assert "dependency_audit" in content
    assert "cicd_audit" in content
    assert "github_token_env=github_token_env" in content


def test_assessment_file_size():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 200


def test_dependency_audit_file_size():
    with open(DEPENDENCY, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 100


def test_dependency_audit_contains_functions_and_fields():
    with open(DEPENDENCY, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def audit_dependencies" in content
    assert "_run_pip_audit" in content
    assert "_run_npm_audit" in content
    assert "vulnerabilities_found" in content
    assert "critical_count" in content
    assert "high_count" in content


def test_synthesis_file_size():
    with open(SYNTHESIS, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 70


def test_synthesis_contains_key_logic():
    with open(SYNTHESIS, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def synthesize_recommendations" in content
    assert "cicd_static" in content
    assert "cicd_history" in content
    assert "critical_count" in content
    assert "high_count" in content
    assert "vulnerabilities_found" in content


def test_reporting_contains_write_function():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def write_assessment_reports(" in content


def test_reporting_writes_key_files():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "assessment_latest.json" in content
    assert "assessment_latest.md" in content
    assert "assessment_latest.html" in content
    assert "evidence_manifest.json" in content


def test_reporting_contains_dependency_details():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "dependency_details" in content


def test_pycompile_assessment():
    py_compile.compile(str(ASSESSMENT), doraise=True)


def test_pycompile_reporting():
    py_compile.compile(str(REPORTING), doraise=True)


def test_pycompile_dependency():
    py_compile.compile(str(DEPENDENCY), doraise=True)


def test_pycompile_synthesis():
    py_compile.compile(str(SYNTHESIS), doraise=True)
