from __future__ import annotations

from pathlib import Path
from typing import Any

import nico.cli as legacy
import nico.cli_entrypoint as entrypoint
from nico.local_runtime_config import DB_PATH
from nico.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
CLI_MODULE = ROOT / "nico" / "cli.py"


def test_cli_module_is_a_compatibility_facade_not_an_operational_monolith() -> None:
    source = CLI_MODULE.read_text(encoding="utf-8")

    assert "from nico.cli_entrypoint import main" in source
    assert "from nico.local_store import DEFAULT_POLICY, LocalStore" in source
    assert "from nico.local_scan_engine import (" in source
    assert "from nico.local_scan_service import ensure_test_lab, run_scan, scan_drift_demo, scan_test_lab" in source
    assert "from nico.local_scoring_repair_service import (" in source
    assert "from nico.local_reporting_service import (" in source
    assert "from nico.local_verification_service import (" in source
    assert "from nico.local_memory_service import memory_summary as _memory_summary" in source

    for implementation_marker in (
        "import argparse",
        "import sqlite3",
        "CREATE TABLE",
        "executescript(",
        "rglob(\"*\")",
        "re.compile(",
        "def scan_repo(",
        "def detect_drift(",
        "def analyze_memory(",
    ):
        assert implementation_marker not in source


def test_legacy_store_constructor_and_constants_remain_compatible(tmp_path: Path) -> None:
    store = legacy.Store(tmp_path / "legacy.sqlite3")

    assert isinstance(store, LocalStore)
    assert legacy.DB_PATH == DB_PATH
    assert legacy.DEFAULT_POLICY == LocalStore(tmp_path / "policy.sqlite3").policy()
    assert legacy.fp("value") == legacy.fingerprint("value")
    assert legacy._allowed_scan_bases is legacy.allowed_scan_bases
    assert legacy._safe_scan_root is legacy.safe_scan_root


def test_repair_wrapper_preserves_legacy_monkeypatch_identity_and_time(monkeypatch) -> None:
    ids = iter(["repair_exact_1", "repair_exact_2", "repair_exact_3"])
    monkeypatch.setattr(legacy, "new_id", lambda prefix: next(ids))
    monkeypatch.setattr(legacy, "now", lambda: "2026-07-13T23:59:00+00:00")
    finding = {
        "id": "finding_exact_1",
        "category": "debug_mode",
        "severity": "high",
        "title": "Debug mode enabled",
        "affected_file": "app.py",
        "verification_method": "pytest tests/test_app.py",
        "rye": {"score": 72.0},
    }

    repairs = legacy.repairs_for([finding])

    assert [item["id"] for item in repairs] == [
        "repair_exact_1",
        "repair_exact_2",
        "repair_exact_3",
    ]
    assert all(item["created_at"] == "2026-07-13T23:59:00+00:00" for item in repairs)
    assert all(item["status"] == "suggested" for item in repairs)


def test_reporting_memory_and_verification_wrappers_use_legacy_store_seam(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")
    scan = {
        "id": "scan_exact_1",
        "created_at": "2026-07-13T23:59:00+00:00",
        "files_scanned": [],
        "findings": [],
    }
    store.save_scan(scan, "local")
    monkeypatch.setattr(legacy, "Store", lambda: store)
    monkeypatch.setattr(legacy, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(legacy, "new_id", lambda prefix: f"{prefix}_exact_1")
    monkeypatch.setattr(legacy, "now", lambda: "2026-07-13T23:59:01+00:00")

    paths = legacy.generate_reports()
    verification = legacy.verify_latest()
    memory = legacy.memory_summary()

    assert {item["format"] for item in paths} == {
        "json",
        "markdown",
        "html",
        "owner",
        "developer",
        "reparodynamic",
        "compliance",
    }
    assert legacy.report_text("owner").startswith("# NICO Owner Report")
    assert verification["id"] == "verify_exact_1"
    assert verification["scan_id"] == "scan_exact_1"
    assert verification["baseline_update_allowed"] is False
    assert memory["items"]


def test_legacy_cli_entrypoint_and_public_surface_remain_available() -> None:
    expected = {
        "Store",
        "scan_text",
        "scan_repo",
        "risk_score",
        "make_baseline",
        "detect_drift",
        "rye_score",
        "apply_rye",
        "repairs_for",
        "analyze_memory",
        "generate_reports",
        "report_text",
        "run_scan",
        "scan_test_lab",
        "scan_drift_demo",
        "verify_latest",
        "verify_repair_by_id",
        "memory_summary",
        "main",
    }

    assert legacy.main is entrypoint.main
    assert expected <= set(legacy.__all__)
    assert all(callable(getattr(legacy, name)) for name in expected)
