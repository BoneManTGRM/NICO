from __future__ import annotations

from copy import deepcopy

import pytest

from nico import express_async_api as api
from nico import lifecycle_status_hardening as hardening
from nico.api import main as api_main
from nico.express_status_liveness_patch import (
    _TERMINAL_PREWRITE_OWNER_MARKER,
    install_express_status_liveness_patch,
)
from nico.storage import MemoryAdapter


class FinalRichWriteFailureStore(MemoryAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.fail_assessment_writes = False

    def put(self, table: str, item_id: str, payload: dict) -> dict:
        if self.fail_assessment_writes and table == "assessment_runs":
            raise RuntimeError("simulated rich final assessment write failure")
        return super().put(table, item_id, payload)


def _request() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_prewrite",
        "project_id": "project_prewrite",
    }


def _terminal(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_prewrite",
        "project_id": "project_prewrite",
        "status": "review_required",
        "technical_score": 78,
        "sections": [{"id": "repository", "score": 80}],
        "reports": {
            "markdown": "# Express report",
            "html": "<!doctype html><html><body>Express report</body></html>",
            "pdf_base64": "JVBERi0xLjQK",
        },
    }


def _stale_checkpoint(run_id: str) -> dict:
    response = _terminal(run_id)
    response.update(
        {
            "status": "running",
            "current_stage": "truth_and_review_gates",
            "progress_percent": 94,
            "report_generation_status": "running",
            "worker_started": True,
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        }
    )
    return response


def test_terminal_progress_is_persisted_before_rich_final_storage(monkeypatch) -> None:
    store = FinalRichWriteFailureStore()
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)
    run_id = "express_run_terminal_prewrite"
    request = _request()
    stale = _stale_checkpoint(run_id)
    store.put(
        "assessment_runs",
        run_id,
        {
            "workflow": "express",
            "run_id": run_id,
            "status": "running",
            "repository": request["repository"],
            "customer_id": request["customer_id"],
            "project_id": request["project_id"],
            "request": deepcopy(request),
            "response": deepcopy(stale),
            "payload": deepcopy(stale),
        },
    )

    def safe_response(value):
        return deepcopy(value) if isinstance(value, dict) else {"status": "unknown"}

    monkeypatch.setattr(api_main, "safe_assessment_response_payload", safe_response)

    def base_status(run: str, customer_id: str, project_id: str) -> dict:
        record = store.get("assessment_runs", run)
        assert isinstance(record, dict)
        assert record["customer_id"] == customer_id
        assert record["project_id"] == project_id
        return deepcopy(record["response"])

    monkeypatch.setattr(hardening, "_express_status_response", base_status)
    installed = install_express_status_liveness_patch()

    assert installed["terminal_progress_prewrite"]["owner_verified"] is True
    assert getattr(api_main.safe_assessment_response_payload, _TERMINAL_PREWRITE_OWNER_MARKER, None) is api_main.safe_assessment_response_payload

    terminal = api_main.safe_assessment_response_payload(_terminal(run_id))
    assert terminal["status"] == "complete"
    assert terminal["current_stage"] == "complete"
    assert terminal["progress_percent"] == 100
    assert terminal["report_generation_status"] == "complete"

    progress = store.get("express_run_progress", run_id)
    assert isinstance(progress, dict)
    assert progress["terminal_success_ready"] is True
    assert progress["report_formats_ready"] is True

    # Reproduce the production failure boundary: the compact terminal record is
    # already durable when the subsequent rich assessment-record write fails.
    store.fail_assessment_writes = True
    with pytest.raises(RuntimeError, match="rich final assessment write failure"):
        store.put("assessment_runs", run_id, {"status": "complete", "payload": terminal})

    response = hardening._express_status_response(
        run_id,
        request["customer_id"],
        request["project_id"],
    )
    assert response["status"] == "complete"
    assert response["current_stage"] == "complete"
    assert response["progress_percent"] == 100
    assert response["technical_score"] == 78
    assert response["reports"]["pdf_base64"] == "JVBERi0xLjQK"
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False
    assert response["progress_reconciliation"]["terminal_success_recovered"] is True


def test_terminal_prewrite_refuses_incomplete_report_formats(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)
    monkeypatch.setattr(api_main, "safe_assessment_response_payload", lambda value: deepcopy(value))
    monkeypatch.setattr(hardening, "_express_status_response", lambda _run, _customer, _project: {})

    install_express_status_liveness_patch()
    run_id = "express_run_incomplete_terminal_prewrite"
    incomplete = _terminal(run_id)
    incomplete["reports"]["pdf_base64"] = ""

    output = api_main.safe_assessment_response_payload(incomplete)

    assert output["status"] == "review_required"
    assert store.get("express_run_progress", run_id) is None
