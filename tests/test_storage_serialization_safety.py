from __future__ import annotations

import json
from pathlib import Path

import nico.durable_runtime_storage as durable
import nico.express_async_api as express
import nico.express_backend_diagnostics as diagnostics
import nico.express_snapshot_pipeline as pipeline
import nico.storage as storage
from nico.storage_serialization_safety import (
    install_storage_serialization_safety,
    json_safe_storage_payload,
)


def _contains_marker(value, marker: str) -> bool:
    if isinstance(value, dict):
        return marker in value or any(_contains_marker(item, marker) for item in value.values())
    if isinstance(value, list):
        return any(_contains_marker(item, marker) for item in value)
    return False


def test_json_safe_storage_payload_breaks_cycles_but_preserves_shared_noncyclic_values() -> None:
    shared = {"value": 7}
    payload = {"first": shared, "second": shared}
    payload["self"] = payload

    safe = json_safe_storage_payload(payload)

    assert safe["first"] == {"value": 7}
    assert safe["second"] == {"value": 7}
    assert safe["self"] == {"$circular_reference": "dict"}
    json.dumps(safe, sort_keys=True, allow_nan=False)


def test_sqlite_put_retains_bounded_circular_evidence_instead_of_raising(tmp_path: Path) -> None:
    install_storage_serialization_safety()
    adapter = durable.SQLiteRuntimeAdapter(tmp_path / "runtime.sqlite3")
    scanner = {"scan_id": "scan_cycle", "status": "running", "scanner_results": []}
    scanner["scanner_results"].append(scanner)
    record = {
        "run_id": "express_run_cycle",
        "workflow": "express",
        "status": "running",
        "response": {"status": "running", "scanner": scanner},
    }

    saved = adapter.put("assessment_runs", "express_run_cycle", record)
    retained = adapter.get("assessment_runs", "express_run_cycle")

    assert saved["run_id"] == "express_run_cycle"
    assert retained is not None
    assert _contains_marker(retained, "$circular_reference")
    json.dumps(retained, sort_keys=True, allow_nan=False)


def test_express_safe_scan_is_cycle_safe_and_redacts_secret_shapes() -> None:
    install_storage_serialization_safety()
    secret = "ghp_" + "1234567890" + "abcdefghijklmnop"
    scanner = {
        "scan_id": "scan_cycle",
        "run_id": "express_run_cycle",
        "status": "running",
        "current_stage": "scanner_suite",
        "scanner_results": [],
        "unavailable_data_notes": [secret],
    }
    scanner["scanner_results"].append(scanner)

    safe = pipeline._safe_scan(scanner)
    serialized = json.dumps(safe, sort_keys=True, allow_nan=False)

    assert "$circular_reference" in serialized
    assert secret not in serialized
    assert "[REDACTED]" in serialized


def test_live_scanner_progress_with_cycle_persists_to_sqlite(monkeypatch, tmp_path: Path) -> None:
    install_storage_serialization_safety()
    adapter = durable.SQLiteRuntimeAdapter(tmp_path / "runtime.sqlite3")
    monkeypatch.setattr(express, "STORE", adapter)
    scanner = {
        "scan_id": "scan_snapshot_cycle",
        "run_id": "express_run_cycle",
        "status": "running",
        "current_stage": "scanner_suite",
        "progress_percent": 53,
        "active_tool": "semgrep",
        "scanner_results": [],
    }
    scanner["scanner_results"].append(scanner)

    response = diagnostics._publish_live_stage(
        "express_run_cycle",
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_cody_jenkins",
            "project_id": "project_nico_audit",
            "authorized": True,
            "authorization_confirmed": True,
        },
        ui_stage="scanner_reconciliation",
        backend_stage="wait_snapshot_scanner",
        message="Exact-snapshot scanner is running semgrep.",
        worker_started_at="2099-01-01T00:00:00Z",
        scanner=scanner,
        snapshot={"snapshot_id": "snapshot_cycle", "commit_sha": "a" * 40},
    )
    retained = adapter.get("assessment_runs", "express_run_cycle")

    assert response["status"] == "running"
    assert retained is not None
    assert retained["status"] == "running"
    assert retained["response"]["scanner"]["active_tool"] == "semgrep"
    assert _contains_marker(retained["response"]["scanner"], "$circular_reference")


def test_installer_rebinds_both_storage_modules_and_express_scanner_boundary() -> None:
    status = install_storage_serialization_safety()

    assert status["storage_metadata_boundary_installed"] is True
    assert status["sqlite_metadata_boundary_installed"] is True
    assert status["express_scanner_boundary_installed"] is True
    assert status["circular_reference_is_terminal"] is False
    assert storage._with_default_metadata is durable._with_default_metadata
