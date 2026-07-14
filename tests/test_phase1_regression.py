"""Phase 1 Regression Protection Tests

These tests protect the working NICO foundation from accidental overwrites or truncation.
Run these before any major changes.
"""

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "nico" / "cli.py"
LOCAL_STORE_PATH = REPO_ROOT / "nico" / "local_store.py"
LOCAL_SCAN_ENGINE_PATH = REPO_ROOT / "nico" / "local_scan_engine.py"
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


def test_cli_py_exists_and_is_bounded_compatibility_facade():
    assert CLI_PATH.exists(), "nico/cli.py is missing"
    content = CLI_PATH.read_text(encoding="utf-8")
    assert 3000 < len(content) < 9000, "nico/cli.py facade size is outside the expected bounded range"
    assert "from nico.cli_entrypoint import main" in content
    assert "from nico.local_scan_engine import (" in content
    assert "from nico.local_store import DEFAULT_POLICY, LocalStore" in content
    assert "import sqlite3" not in content
    assert "CREATE TABLE" not in content
    assert "executescript(" not in content


def test_required_symbols_are_exported_by_cli_facade():
    module = importlib.import_module("nico.cli")
    for symbol in REQUIRED_SYMBOLS:
        assert hasattr(module, symbol), f"Required compatibility symbol '{symbol}' missing from nico.cli"
        assert callable(getattr(module, symbol)), f"Compatibility symbol '{symbol}' is not callable"


def test_auditor_imports_compatibility_facade():
    assert AUDITOR_PATH.exists(), "nico/auditor.py is missing"
    content = AUDITOR_PATH.read_text(encoding="utf-8")
    assert "from nico.cli import" in content, "nico/auditor.py does not import from the compatibility facade"
    assert "run_scan" in content, "run_scan not imported in auditor"
    assert "generate_reports" in content, "generate_reports not imported in auditor"


def test_extracted_store_payloads_uses_self_rows():
    content = LOCAL_STORE_PATH.read_text(encoding="utf-8")
    assert "def payloads(self, table:" in content
    assert "self.rows(table)" in content, "payloads() must call self.rows(table)"


def test_scan_engine_and_test_lab_entrypoint_remain_available():
    engine_content = LOCAL_SCAN_ENGINE_PATH.read_text(encoding="utf-8")
    assert "def scan_repo(" in engine_content
    assert "def normalized_finding(" in engine_content

    module = importlib.import_module("nico.cli")
    assert callable(module.ensure_test_lab)


def test_existing_commands_still_work():
    from nico.cli import generate_reports, scan_drift_demo, scan_test_lab, verify_latest

    assert callable(scan_test_lab)
    assert callable(scan_drift_demo)
    assert callable(verify_latest)
    assert callable(generate_reports)
