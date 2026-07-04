"""Phase 1 Regression Protection Tests

These tests protect the working NICO foundation from accidental overwrites or truncation.
Run these before any major changes.
"""

import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "nico" / "cli.py"
AUDITOR_PATH = REPO_ROOT / "nico" / "auditor.py"

REQUIRED_SYMBOLS = [
    "scan_repo",
    "run_scan",
    "scan_test_lab",
    "scan_drift_demo",
    "generate_reports",
    "rye_score",
    "Store",
    "verify_latest",
    "normalized_finding",
    "apply_rye",
    "repairs_for",
]


def test_cli_py_exists_and_not_truncated():
    assert CLI_PATH.exists(), "nico/cli.py is missing"
    content = CLI_PATH.read_text(encoding="utf-8")
    assert len(content) > 8000, "nico/cli.py appears truncated (too short)"
    assert "def main(" in content, "main() function missing in nico/cli.py"


def test_required_symbols_exist_in_cli():
    content = CLI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content)
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) or isinstance(node, ast.ClassDef)}
    for symbol in REQUIRED_SYMBOLS:
        assert symbol in names, f"Required symbol '{symbol}' missing from nico/cli.py"


def test_auditor_imports_real_engine():
    assert AUDITOR_PATH.exists(), "nico/auditor.py is missing"
    content = AUDITOR_PATH.read_text(encoding="utf-8")
    assert "from nico.cli import" in content, "nico/auditor.py does not import from nico.cli"
    assert "run_scan" in content, "run_scan not imported in auditor"
    assert "generate_reports" in content, "generate_reports not imported in auditor"


def test_payloads_uses_self_rows():
    content = CLI_PATH.read_text(encoding="utf-8")
    assert "def payloads(self, table:" in content
    assert "self.rows(table)" in content, "payloads() must call self.rows(table)"


def test_ensure_test_lab_syntax_valid():
    # Just ensure the file compiles
    spec = importlib.util.spec_from_file_location("cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "ensure_test_lab"), "ensure_test_lab missing"


def test_existing_commands_still_work():
    # These should at least be importable and have the right signatures
    from nico.cli import scan_test_lab, scan_drift_demo, verify_latest, generate_reports
    assert callable(scan_test_lab)
    assert callable(scan_drift_demo)
    assert callable(verify_latest)
    assert callable(generate_reports)
