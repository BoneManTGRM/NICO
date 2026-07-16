from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import nico.express_async_api as express
import nico.express_backend_diagnostics as diagnostics
from nico.storage import MemoryAdapter


class RequestModel:
    def __init__(self, **payload):
        self.payload = payload

    def model_dump(self):
        return deepcopy(self.payload)


def _request() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": "requester_confirmation",
        "authorization_scope": "repository assessment only",
        "customer_id": "customer_stage_progress",
        "project_id": "project_stage_progress",
        "client_name": "Stage Test",
        "project_name": "Express Lifecycle",
        "refresh_full_evidence": True,
    }


def _snapshot(run_id: str) -> dict:
    return {
        "status": "attached",
        "snapshot_id": f"snapshot_{run_id}",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "default_branch": "main",
        "captured_at": "2026-07-16T02:40:00Z",
    }


def _scan(run_id: str, status: str = "complete", progress: int = 100) -> dict:
    return {
        "scan_id": f"scan_snapshot_{run_id[-12:]}",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_stage_progress",
        "project_id": "project_stage_progress",
        "status": status,
        "current_stage": "complete" if status == "complete" else "scanner_suite",
        "progress_percent": progress,
        "active_tool": "" if status == "complete" else "semgrep",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": "a" * 40,
        "actual_commit_sha": "a" * 40 if status == "complete" else "",
        "snapshot_match": status == "complete",
        "tools_requested": ["pip-audit", "semgrep", "trufflehog"],
        "tools_run": ["pip-audit", "semgrep", "trufflehog"] if status == "complete" else [],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "scanner_results": [
            {"tool": "pip-audit", "status": "completed", "category": "dependency", "findings": []},
            {"tool": "semgrep", "status": "completed", "category": "static", "findings": []},
            {"tool": "trufflehog", "status": "completed", "category": "secret", "findings": []},
        ] if status == "complete" else [],
        "heartbeat_at": "2026-07-16T02:41:00Z",
        "heartbeat_sequence": 3,
    }


def _install_scanner_fakes(monkeypatch, run_id: str) -> tuple[dict, dict]:
    snapshot = _snapshot(run_id)
    initial = _scan(run_id, "queued", 2)
    complete = _scan(run_id)

    monkeypatch.setattr(diagnostics, "start_express_snapshot_scan", lambda _run_id, _payload: (deepcopy(snapshot), deepcopy(initial)))

    def wait(_run_id, _snapshot_value, _initial, *, on_update=None):
        if on_update:
            on_update(_scan(run_id, "running", 47))
            on_update(deepcopy(complete))
        return deepcopy(complete)

    monkeypatch.setattr(diagnostics, "wait_for_express_snapshot_scan", wait)

    def attach(result, snapshot_value, scan_value):
        output = deepcopy(result)
        output["repository_snapshot"] = deepcopy(snapshot_value)
        output["scanner"] = deepcopy(scan_value)
        output["scanner_run"] = deepcopy(scan_value)
        output["scanner_results"] = deepcopy(scan_value["scanner_results"])
        output["worker_evidence_attachment"] = {
            "status": "complete",
            "mode": "exact_same_run_snapshot_bound",
            "run_id": run_id,
            "scan_id": scan_value["scan_id"],
            "snapshot_match": True,
        }
        return output

    monkeypatch.setattr(diagnostics, "attach_exact_express_scanner_evidence", attach)
    return snapshot, complete


def test_express_worker_publishes_truthful_stage_sequence_and_scanner_state(monkeypatch) -> None:
    store = MemoryAdapter()
    run_id = "express_run_truthful_stage_progress"
    request = _request()
    observed: list[dict] = []

    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(diagnostics.express, "STORE", store)
    original_record = express._record

    def capturing_record(record_run_id: str, payload: dict, response: dict):
        observed.append(deepcopy(response))
        return original_record(record_run_id, payload, response)

    monkeypatch.setattr(express, "_record", capturing_record)
    monkeypatch.setattr(diagnostics.express, "_record", capturing_record)
    monkeypatch.setattr(diagnostics, "_clear_request_local_payload", lambda: None)
    snapshot, completed_scan = _install_scanner_fakes(monkeypatch, run_id)

    markdown = "# Express report\n\n" + ("Evidence-bound scanner-backed report content. " * 30)
    html = "<!doctype html><html><body>" + ("<p>Evidence-bound scanner-backed report content.</p>" * 20) + "</body></html>"
    base_result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "sections": [{"id": "summary", "label": "Summary", "evidence": ["Repository evidence"]}],
        "reports": {
            "report_id": "express_report_truthful_stage_progress",
            "markdown": markdown,
            "html": html,
            "pdf_base64": "JVBERi0xLjQK" + ("A" * 200),
        },
    }

    def attach_review(result, _payload):
        output = deepcopy(result)
        output["report_id"] = "express_report_truthful_stage_progress"
        return output

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=lambda _payload: deepcopy(base_result),
        run_github_assessment_with_scanner_artifacts=lambda _payload: deepcopy(base_result),
        enrich_payload_with_scanner_evidence=lambda result: deepcopy(result),
        apply_report_accuracy=lambda result: deepcopy(result),
        attach_express_review_target=attach_review,
        polish_express_result=lambda result: deepcopy(result),
        finalize_express_result_consistency=lambda result: deepcopy(result),
        attach_evidence_artifact_bundle=lambda result: {
            **deepcopy(result),
            "evidence_artifact_bundle": {"bundle_hash": "bundle_truthful_stage"},
        },
        attach_client_acceptance_gate=lambda result: {
            **deepcopy(result),
            "human_review_required": True,
            "client_ready": False,
        },
        safe_assessment_response_payload=lambda result: deepcopy(result),
        _LAST_HOSTED_ASSESSMENT={},
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)

    express._ACTIVE_RUNS.add(run_id)
    express._ACTIVE_SCOPE_RUNS[express._scope_key(request)] = run_id
    diagnostics.execute_with_diagnostics(run_id, request)

    latest_by_stage = {str(item.get("current_stage")): item for item in observed}
    expected = {
        "repository_evidence": 14,
        "scanner_reconciliation": 48,
        "accuracy_review": 62,
        "score_reconciliation": 72,
        "report_generation": 82,
        "truth_and_review_gates": 94,
        "complete": 100,
    }
    assert {stage: latest_by_stage[stage]["progress_percent"] for stage in expected} == expected

    repository = latest_by_stage["repository_evidence"]
    assert repository["worker_started"] is True
    assert repository["worker_started_at"]
    assert repository["worker_process_id"] > 0
    assert repository["worker_thread"]
    assert repository["status_truth"] == "durable_worker_stage"
    assert repository["scanner"]["status"] == "queued"
    assert repository["scan_id"] == completed_scan["scan_id"]
    assert repository["snapshot_commit_sha"] == snapshot["commit_sha"]

    scanner = latest_by_stage["scanner_reconciliation"]
    assert scanner["scanner"]["status"] == "complete"
    assert scanner["scanner"]["snapshot_match"] is True
    assert scanner["backend_stage"] == "attach_exact_scanner_evidence"

    final = latest_by_stage["complete"]
    assert final["status"] == "complete"
    assert final["scanner"]["status"] == "complete"
    assert final["scanner"]["snapshot_match"] is True
    assert final["worker_evidence_attachment"]["mode"] == "exact_same_run_snapshot_bound"
    assert final["reports"]["report_id"] == "express_report_truthful_stage_progress"
    assert final["reports"]["pdf_base64"]
    assert final["human_review_required"] is True
    assert final["client_ready"] is False
    assert run_id not in express._ACTIVE_RUNS


def test_backend_diagnostic_failure_is_terminal_not_request_accepted(monkeypatch) -> None:
    store = MemoryAdapter()
    run_id = "express_run_terminal_diagnostic_progress"
    request = _request()
    monkeypatch.setattr(express, "STORE", store)
    monkeypatch.setattr(diagnostics.express, "STORE", store)
    monkeypatch.setattr(diagnostics, "_clear_request_local_payload", lambda: None)
    _install_scanner_fakes(monkeypatch, run_id)

    class BackendFailure(RuntimeError):
        pass

    fake_main = SimpleNamespace(
        GithubAssessmentRequest=RequestModel,
        extract_scanner_worker_artifact=lambda _payload: {},
        run_github_assessment=lambda _payload: (_ for _ in ()).throw(BackendFailure("private failure")),
        run_github_assessment_with_scanner_artifacts=lambda _payload: {},
    )
    monkeypatch.setattr(express, "import_module", lambda _name: fake_main)

    express._ACTIVE_RUNS.add(run_id)
    express._ACTIVE_SCOPE_RUNS[express._scope_key(request)] = run_id
    diagnostics.execute_with_diagnostics(run_id, request)

    response = store.get("assessment_runs", run_id)["response"]
    assert response["status"] == "failed"
    assert response["progress_percent"] == 100
    assert response["current_stage"] == "failed"
    assert response["failure_stage"] == "collect_assessment"
    assert response["code"] == "express_backend_execution_failed"
    assert "private failure" not in repr(response)


def test_express_never_publishes_complete_without_report_artifacts(monkeypatch) -> None:
    result = {
        "scanner": _scan("express_run_missing_report"),
        "worker_evidence_attachment": {
            "status": "complete",
            "mode": "exact_same_run_snapshot_bound",
        },
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }

    try:
        diagnostics._validate_final_artifacts(result)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert exc.detail["code"] == "express_report_artifacts_missing"
    else:
        raise AssertionError("Expected Express report artifact gate to block completion")
