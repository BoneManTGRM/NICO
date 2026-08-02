from __future__ import annotations

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.comprehensive_retained_scanner_evidence_v1 import (
    compact_scanner_records,
    retained_scanner_payload,
)
from nico.comprehensive_scanner_stage_retention_v1 import (
    install_scanner_stage_retention,
)
from nico.v2_scanner_reconciliation import normalize_record

SHA = "a" * 40
TOOLS = ["bandit", "eslint"]


def _scan() -> dict:
    return {
        "scan_id": "scan-retained",
        "snapshot_commit_sha": SHA,
        "actual_commit_sha": SHA,
        "snapshot_match": True,
        "tools_requested": list(TOOLS),
        "tools_run": list(TOOLS),
        "failed_tools": [],
        "unavailable_tools": [],
        "timed_out_tools": [],
        "finding_summary": {
            "by_tool": {
                "bandit": {"raw": 2, "material": 1, "review_required": 1},
                "eslint": {"raw": 0, "material": 0, "review_required": 0},
            }
        },
        "scanner_results": [
            {
                "tool": "bandit",
                "status": "completed",
                "returncode": 1,
                "findings": [{"test_id": "B101"}, {"test_id": "B602"}],
                "artifact_hash": "b" * 64,
                "raw_artifact_retention_complete": True,
                "verified_for_this_report": True,
                "commit_sha": SHA,
            },
            {
                "tool": "eslint",
                "status": "completed",
                "returncode": 0,
                "findings": [],
                "artifact_hash": "e" * 64,
                "raw_artifact_retention_complete": True,
                "verified_for_this_report": True,
                "commit_sha": SHA,
            },
        ],
    }


def _context() -> dict:
    return {
        "run_id": "comprun-retained",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": SHA,
        "evidence_ledger_id": "ledger-retained",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": {},
    }


def test_compact_records_preserve_hash_status_and_count_without_raw_findings() -> None:
    records = compact_scanner_records(_scan(), commit_sha=SHA)
    by_name = {item["scanner_name"]: item for item in records}

    assert by_name["bandit"]["artifact_hash"] == "b" * 64
    assert by_name["bandit"]["finding_count"] == 2
    assert by_name["bandit"]["findings"] == []
    assert by_name["bandit"]["raw_findings_embedded"] is False
    assert by_name["bandit"]["evidence_reference"] == "scanner_runs/scan-retained"
    assert by_name["eslint"]["artifact_hash"] == "e" * 64
    assert by_name["eslint"]["finding_count"] == 0

    normalized = normalize_record(by_name["bandit"], SHA)
    assert normalized["status"] == "completed_with_findings"
    assert normalized["completed"] is True
    assert normalized["verified_complete"] is True


def test_scanner_provider_wrapper_retains_compact_records(monkeypatch) -> None:
    from nico import comprehensive_native_providers as native

    monkeypatch.setattr(native, "_scan", lambda context: _scan())
    app = FastAPI()

    def scanner_provider(context: dict) -> dict:
        return {
            "status": "complete",
            "scan_id": "scan-retained",
            "scanner": {
                "scan_id": "scan-retained",
                "status": "complete",
                "snapshot_match": True,
                "actual_commit_sha": SHA,
                "tools_requested": list(TOOLS),
                "tools_run": list(TOOLS),
                "failed_tools": [],
                "unavailable_tools": [],
                "timed_out_tools": [],
            },
            "evidence": {},
        }

    setattr(app.state, PROVIDER_STATE_KEY, {"scanner_suite": scanner_provider})
    installed = install_scanner_stage_retention(app)
    assert installed["bound"] is True

    wrapped = getattr(app.state, PROVIDER_STATE_KEY)["scanner_suite"]
    result = wrapped(_context())
    assert result["status"] == "complete"
    assert len(result["scanner_execution_records"]) == 2
    assert result["scanner_artifact_retention"]["compact_records_only"] is True
    assert result["scanner_artifact_retention"]["raw_findings_embedded"] is False
    assert result["scanner_artifact_retention"]["available_to_final_report_without_scanner_store_read"] is True


def test_final_payload_uses_retained_records_without_scanner_store_access(monkeypatch) -> None:
    from nico import comprehensive_native_providers as native

    def forbidden(_context):
        raise AssertionError("final report must not read scanner store")

    monkeypatch.setattr(native, "_scan", forbidden)
    records = compact_scanner_records(_scan(), commit_sha=SHA)
    context = _context()
    context["prior_stage_results"] = {
        "dependency_security_static_analysis": {
            "status": "complete",
            "scan_id": "scan-retained",
            "scanner": {
                "scan_id": "scan-retained",
                "status": "complete",
                "snapshot_match": True,
                "actual_commit_sha": SHA,
                "tools_requested": list(TOOLS),
                "tools_run": list(TOOLS),
                "failed_tools": [],
                "unavailable_tools": [],
                "timed_out_tools": [],
                "finding_summary": _scan()["finding_summary"],
            },
            "scanner_execution_records": records,
        }
    }

    payload = retained_scanner_payload(context)
    assert payload["source"] == "retained_exact_run_compact_records"
    assert payload["record_count"] == 2
    assert payload["verified_record_count"] == 2
    assert payload["final_stage_scanner_store_read"] is False
    assert payload["final_stage_scanner_execution"] is False
    assert payload["raw_scanner_outputs_embedded"] is False


def test_missing_compact_records_remain_partial_and_do_not_trigger_hidden_scan() -> None:
    context = _context()
    context["prior_stage_results"] = {
        "dependency_security_static_analysis": {
            "status": "complete",
            "scan_id": "scan-manifest-only",
            "scanner": {
                "scan_id": "scan-manifest-only",
                "status": "complete",
                "snapshot_match": True,
                "actual_commit_sha": SHA,
                "tools_requested": list(TOOLS),
                "tools_run": list(TOOLS),
                "failed_tools": [],
                "unavailable_tools": [],
                "timed_out_tools": [],
            },
        }
    }

    payload = retained_scanner_payload(context)
    assert payload["source"] == "retained_exact_run_manifest_without_artifacts"
    assert payload["record_count"] == 2
    assert payload["verified_record_count"] == 0
    assert all(item["completed"] is False for item in payload["scanner_execution_records"])
    assert all(item["status"] == "partial" for item in payload["scanner_execution_records"])
