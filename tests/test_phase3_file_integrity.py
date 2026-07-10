"""Phase 3 File Integrity Regression Test

Comprehensive guard against truncation of all critical NICO files.
"""

import py_compile
from pathlib import Path

from nico.assessment import run_assessment

ASSESSMENT = Path("nico/assessment.py")
REPORTING = Path("nico/modules/reporting.py")
DEPENDENCY = Path("nico/modules/dependency_audit.py")
SYNTHESIS = Path("nico/modules/synthesis.py")
MATURITY = Path("nico/modules/maturity.py")
ROADMAP = Path("nico/modules/roadmap.py")
CLI = Path("nico/cli.py")
PACKAGE_INIT = Path("nico/__init__.py")
SITECUSTOMIZE = Path("sitecustomize.py")


def test_assessment_file_size_and_start():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 200
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("#!/", "\"\"\"", "import ", "from ")) for line in first_lines)


def test_assessment_has_key_functions():
    with open(ASSESSMENT, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def run_assessment(" in content
    assert "def main(" in content


def test_assessment_contains_all_modules():
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


def test_reporting_file_size_and_start():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 180
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("\"\"\"", "import ", "from ")) for line in first_lines)


def test_reporting_has_write_function():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def write_assessment_reports(" in content


def test_reporting_writes_all_outputs():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "assessment_latest.json" in content
    assert "assessment_latest.md" in content
    assert "assessment_latest.html" in content
    assert "evidence_manifest.json" in content


def test_reporting_contains_all_sections():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "## Dependency Audit" in content
    assert "## CI/CD Audit" in content
    assert "## GitHub Activity" in content
    assert "## GitHub Token Health" in content
    assert "## Ranked Recommendations" in content


def test_reporting_contains_details_objects():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "dependency_details" in content
    assert "cicd_details" in content
    assert "github_token_health_details" in content
    assert "module_statuses" in content
    assert "ranked_recommendations_with_evidence" in content


def test_dependency_file_size_and_start():
    with open(DEPENDENCY, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 100
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("\"\"\"", "import ", "from ")) for line in first_lines)


def test_dependency_contains_functions_and_fields():
    with open(DEPENDENCY, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def audit_dependencies" in content
    assert "_run_pip_audit" in content
    assert "_run_npm_audit" in content
    assert "vulnerabilities_found" in content
    assert "critical_count" in content
    assert "high_count" in content
    assert "KNOWN_RISKY" in content


def test_synthesis_file_size_and_start():
    with open(SYNTHESIS, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 70
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("\"\"\"", "import ", "from ")) for line in first_lines)


def test_synthesis_contains_key_logic():
    with open(SYNTHESIS, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def synthesize_recommendations" in content
    assert "critical_count" in content
    assert "high_count" in content
    assert "vulnerabilities_found" in content
    assert "cicd_static" in content
    assert "cicd_history" in content
    assert "ranked_recommendations" in content


def test_maturity_file_size_and_start():
    with open(MATURITY, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 60
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("\"\"\"", "import ", "from ")) for line in first_lines)


def test_maturity_contains_key_elements():
    with open(MATURITY, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def assess_maturity" in content
    assert "critical_count" in content
    assert "high_count" in content
    assert "vulnerabilities_found" in content
    assert "semaphore" in content
    assert "quick_wins" in content
    assert "drivers" in content


def test_roadmap_file_size_and_start():
    with open(ROADMAP, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 50
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("\"\"\"", "import ", "from ")) for line in first_lines)


def test_roadmap_contains_key_elements():
    with open(ROADMAP, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def build_roadmap" in content
    assert "30_days" in content
    assert "60_days" in content
    assert "90_days" in content
    assert "critical_count" in content
    assert "high_count" in content
    assert "vulnerabilities_found" in content


def test_cli_file_size_and_start():
    with open(CLI, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 450
    assert "[targeted tuple edit]" not in content
    assert "[full content" not in content
    assert "...fixed tuple..." not in content
    assert "placeholder" not in content.lower()
    first_lines = content.splitlines()[:3]
    assert any(line.startswith(("from __future__ import", "import ", "from ")) for line in first_lines)


def test_cli_contains_key_symbols():
    with open(CLI, "r", encoding="utf-8") as f:
        content = f.read()
    assert "from __future__ import annotations" in content
    assert "class Store" in content
    assert "def run_scan" in content
    assert "def apply_rye" in content
    assert "def repairs_for" in content
    assert "def generate_reports" in content
    assert "def scan_test_lab" in content
    assert "def scan_drift_demo" in content
    assert "def verify_latest" in content
    assert "def rye_score" in content
    assert "def main" in content
    assert "APPSEC_PATTERNS" in content
    assert "REPAIR_LIBRARY" in content
    assert "def _safe_scan_root" in content
    assert "def _safe_scan_file" in content
    assert "def _safe_scan_files" in content
    assert "relative_to(root)" in content
    assert "candidate.is_symlink()" in content


def test_pycompile_all_critical_files():
    py_compile.compile(str(ASSESSMENT), doraise=True)
    py_compile.compile(str(REPORTING), doraise=True)
    py_compile.compile(str(DEPENDENCY), doraise=True)
    py_compile.compile(str(SYNTHESIS), doraise=True)
    py_compile.compile(str(MATURITY), doraise=True)
    py_compile.compile(str(ROADMAP), doraise=True)
    py_compile.compile(str(CLI), doraise=True)
    py_compile.compile(str(PACKAGE_INIT), doraise=True)


def test_appsec_patterns_source_tuples_are_7_values():
    import ast

    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    appsec = None

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "APPSEC_PATTERNS":
                    appsec = ast.literal_eval(node.value)

    assert appsec is not None, "APPSEC_PATTERNS not found"
    bad = [item for item in appsec if len(item) != 7]
    assert not bad, f"APPSEC_PATTERNS contains non-7-value tuples: {bad}"


def test_appsec_runtime_normalizers_removed():
    init_content = PACKAGE_INIT.read_text(encoding="utf-8")
    assert "__version__" in init_content
    assert "_normalize_appsec_patterns" not in init_content
    assert "APPSEC_PATTERNS" not in init_content
    assert "sitecustomize" not in init_content.lower()
    assert not SITECUSTOMIZE.exists(), "sitecustomize.py runtime normalizer should be removed"
