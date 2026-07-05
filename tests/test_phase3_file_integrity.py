"""Phase 3 File Integrity Regression Test

Prevents future truncation or corruption of critical files.
"""

import ast

from pathlib import Path


ASSESSMENT_PATH = Path("nico/assessment.py")
REPORTING_PATH = Path("nico/modules/reporting.py")


def _get_source_tree(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return ast.parse(f.read(), filename=str(path))


def test_assessment_has_run_assessment():
    tree = _get_source_tree(ASSESSMENT_PATH)
    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    assert "run_assessment" in func_names


def test_assessment_has_main():
    tree = _get_source_tree(ASSESSMENT_PATH)
    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    assert "main" in func_names


def test_assessment_imports_token_health():
    with open(ASSESSMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "github_token_health" in content


def test_assessment_imports_github_activity():
    with open(ASSESSMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "github_activity" in content


def test_assessment_calls_cicd_with_token_env():
    with open(ASSESSMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "cicd_audit(target, github_token_env=github_token_env)" in content


def test_reporting_has_write_assessment_reports():
    tree = _get_source_tree(REPORTING_PATH)
    func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    assert "write_assessment_reports" in func_names


def test_reporting_writes_assessment_latest_json():
    with open(REPORTING_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "assessment_latest.json" in content


def test_reporting_writes_assessment_latest_md():
    with open(REPORTING_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "assessment_latest.md" in content


def test_reporting_writes_assessment_latest_html():
    with open(REPORTING_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "assessment_latest.html" in content


def test_reporting_writes_evidence_manifest_json():
    with open(REPORTING_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "evidence_manifest.json" in content


def test_reporting_contains_cicd_details():
    with open(REPORTING_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "cicd_details" in content


def test_reporting_contains_github_token_health_details():
    with open(REPORTING_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "github_token_health_details" in content
