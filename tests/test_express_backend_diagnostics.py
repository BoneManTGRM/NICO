from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import nico.express_async_api as express
import nico.express_backend_diagnostics as diagnostics
from nico.storage import MemoryAdapter


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "nico" / "assessment_block_messages.py"


class RequestModel:
    def __init__(self, **payload):
        self.payload = payload

    def model_dump(self):
        return deepcopy(self.payload)


class SecretFailure(RuntimeError):
    pass


def request_payload(**overrides):
    payload = {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": "requester_confirmation",
        "authorization_scope": "repository assessment only",
        "customer_id": "customer_cody_jenkins",
        "project_id": "project_nico_audit",
        "client_name": "Cody Jenkins",
        "project_name": "NICO Audit",
        "refresh_full_evidence": True,
    }
    payload.update(overrides)
    return payload


def _reports(report_id: str) -> dict:
    markdown = "# Express Technical Health Assessment\n\n" + ("Exact-snapshot scanner-backed evidence and recommendations. " * 30)
    html = "<!doctype html><html><body>" + ("<p>Exact-snapshot scanner-backed evidence and recommendations.</p>" * 20) + "</body></html>"
    return {
        "report_id": report_id,
        "markdown": markdown,
        "html": html,
        "pdf_base64": "JVBERi0xLjQK" + ("A" * 240),
    }


def _install_scanner_path(monkeypatch, run_id: str) -> tuple[dict, dict]:
    snapshot = {
        "status": "attached",
        "snapshot_id": f"snapshot_{run_id}",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "default_branch": "main",
        "captured_at": "2026-07-16T03:15:00Z",
    }
    queued = {
        "scan_id": f"scan_{run_id}",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "status": "queued",
        "current_stage": "queued",
        "progress_percent": 2,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_commit_sha": snapshot["commit_sha"],
        "snapshot_match": False,
        "scanner_results": [],
    }
    completed = {
        **queued,
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "actual_commit_sha": snapshot["commit_sha"],
        "snapshot_match": True,
        "tools_requested": ["pip-audit", "semgrep", "trufflehog"],
        "tools_run": ["pip-audit", "semgrep", "trufflehog"],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "scanner_results": [
            {"tool": "pip-audit", "status": "completed", "category": "dependency", "findings": []},
            {"tool": "semgrep", "status": "completed", "category": "static", "findings": []},
            {"tool": "trufflehog", "status": "completed", "category": "secret", "findings": []},
        ],
    }
    monkeypatch.setattr(diagnostics, "start_express_snapshot_scan", lambda _run_id, _payload: (deepcopy(snapshot), deepcopy(queued)))
    monkeypatch.setattr(
        diagnostics,
        "wait_for_express_snapshot_scan",
        lambda _run_id, _snapshot, _initial, on_update=None: deepcopy(completed),
    )

    def attach(result, snapshot_value, scan_value):
        output = deepcopy(result)
        output["repository_snapshot"] = deepcopy(snapshot_value)
        output["scanner"] = deepcopy(scan_value)
        output["scanner_run"] = deepcopy(scan_value)
        output["scanner_results"] = deepcopy(scan_value.get("scanner_results") or [])
        output["worker_evidence_attachment"] = {
            "status": "complete",
            "mode": "exact_same_run_snapshot_bound",
            "run_id": run_id,
            "scan_id": scan_value["scan_id"],
            "snapshot_match": True,
        }
        return output

    monkeypatch.setattr(diagnostics, "attach_exact_express_scanner_evidence", attach)
    return snapshot, completed


@pytest.fixture(autouse=True)
def clear_active_state():
    express._ACTIVE_RUNS.clear()
    express._ACTIVE_SCOPE_RUNS.clear()
    yield
    express._ACTIVE_RUNS.clear()
    express._ACTIVE_SCOPE_RUNS.clear()


def _activate(run_id: str, payload: dict) -> None:
    express._ACTIVE_RUNS.add(run_id)
    express._ACTIVE_SCOPE_RUNS[express._scope_key(payload)] = run_id


def test_unhandled_backend_failure_records_only_bounded_public_diagnostics(monkeypatch, caplog) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(diagnostics.express, "STORE", store)
    run_id = "express_run_exact_failure"
    payload = request_payload()
    _activate(run_id, payload)
    _install_scanner_path(monkeypatch, run_id)

    def fail_assessment(_payload):
        raise SecretFailure("provider token=supersecret raw failure")

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=fail_assessment,
        run_github_assessment_with_scanner_artifacts=fail_assessment,
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)

    with caplog.at_level("ERROR", logger="nico.express_backend_diagnostics"):
        diagnostics.execute_with_diagnostics(run_id, payload)

    record = store.get("assessment_runs", run_id)
    response = record["response"]
    assert response["status"] == "failed"
    assert response["code"] == "express_backend_execution_failed"
    assert response["run_id"] == run_id
    assert response["failure_stage"] == "collect_assessment"
    assert response["exception_class"] == "SecretFailure"
    assert response["diagnostic_id"].startswith("express_diag_")
    assert response["diagnostic_run_id"] == run_id
    assert response["human_review_required"] is True
    assert response["client_ready"] is False
    assert response["progress"][0]["evidence"]["failure_stage"] == "collect_assessment"
    assert response["diagnostic_id"] in response["progress"][0]["message"]
    assert response["exception_class"] in response["progress"][0]["message"]
    assert "supersecret" not in repr(record)
    assert "raw failure" not in repr(record)
    assert response["diagnostic_id"] in caplog.text
    assert run_id not in express._ACTIVE_RUNS
    assert express._scope_key(payload) not in express._ACTIVE_SCOPE_RUNS


def test_success_preserves_request_fields_and_uses_one_exact_final_record(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(diagnostics.express, "STORE", store)
    run_id = "express_run_exact_success"
    payload = request_payload()
    _activate(run_id, payload)
    snapshot, completed_scan = _install_scanner_path(monkeypatch, run_id)

    def attach_review(result, _request):
        output = deepcopy(result)
        output["run_id"] = run_id
        output["report_id"] = "express_report_exact_success"
        output.setdefault("reports", {})["report_id"] = "express_report_exact_success"
        return output

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=lambda _payload: {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "reports": _reports("express_report_exact_success"),
            "sections": [],
        },
        run_github_assessment_with_scanner_artifacts=lambda _payload: {},
        enrich_payload_with_scanner_evidence=lambda result: result,
        apply_report_accuracy=lambda result: result,
        attach_express_review_target=attach_review,
        polish_express_result=lambda result: result,
        finalize_express_result_consistency=lambda result: result,
        attach_evidence_artifact_bundle=lambda result: {
            **result,
            "evidence_artifact_bundle": {"bundle_hash": "bundle_exact"},
        },
        attach_client_acceptance_gate=lambda result: {
            **result,
            "human_review_required": True,
            "client_ready": False,
        },
        safe_assessment_response_payload=lambda result: deepcopy(result),
        hosted_assessment_storage_record=lambda _req: (_ for _ in ()).throw(
            AssertionError("synchronous storage compatibility must not be used by async execution")
        ),
        _LAST_HOSTED_ASSESSMENT={},
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)
    monkeypatch.setattr(diagnostics, "_clear_request_local_payload", lambda: None)

    diagnostics.execute_with_diagnostics(run_id, payload)

    records = store.list("assessment_runs")
    assert len(records) == 1
    record = store.get("assessment_runs", run_id)
    response = record["response"]
    assert response["status"] == "complete"
    assert response["run_id"] == run_id
    assert response["report_id"] == "express_report_exact_success"
    assert response["reports"]["report_id"] == "express_report_exact_success"
    assert response["scanner"]["scan_id"] == completed_scan["scan_id"]
    assert response["scanner"]["snapshot_match"] is True
    assert response["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert response["worker_evidence_attachment"]["mode"] == "exact_same_run_snapshot_bound"
    assert response["human_review_required"] is True
    assert response["client_ready"] is False
    assert fake_main._LAST_HOSTED_ASSESSMENT["run_id"] == run_id
    assert run_id not in express._ACTIVE_RUNS


def test_installer_replaces_worker_idempotently(monkeypatch) -> None:
    def previous_execute(_run_id, _payload):
        return None

    monkeypatch.setattr(express, "_execute", previous_execute)

    first = diagnostics.install_express_backend_diagnostics()
    second = diagnostics.install_express_backend_diagnostics()

    assert first["status"] == "installed"
    assert first["bounded_diagnostics"] is True
    assert first["exact_snapshot_scanner_required"] is True
    assert first["same_run_scanner_identity_required"] is True
    assert first["report_artifact_gate"] is True
    assert first["report_without_scanner_allowed"] is False
    assert first["public_exception_text_exposed"] is False
    assert first["automatic_retry"] is False
    assert first["replacement_run"] is False
    assert second["status"] == "already_installed"
    assert second["exact_snapshot_scanner_required"] is True
    assert second["report_artifact_gate"] is True
    assert express._execute is diagnostics.execute_with_diagnostics


def test_startup_installer_enables_backend_diagnostics_before_routes() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "from nico.express_backend_diagnostics import install_express_backend_diagnostics" in source
    assert "express_diagnostics = install_express_backend_diagnostics()" in source
    assert source.index("express_diagnostics = install_express_backend_diagnostics()") < source.index(
        "express_async = register_express_async_routes(api_main.app)"
    )
    assert '"express_backend_diagnostics": express_diagnostics' in source
