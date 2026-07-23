from __future__ import annotations

from copy import deepcopy

from nico import express_async_api as api
from nico import lifecycle_status_hardening as hardening
from nico.express_status_liveness_patch import (
    _FINAL_RECORD_OWNER_MARKER,
    install_express_status_liveness_patch,
)
from nico.storage import MemoryAdapter


def _request() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_acceptance",
        "project_id": "project_acceptance",
    }


def _terminal(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_acceptance",
        "project_id": "project_acceptance",
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "report_generation_status": "complete",
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
        "technical_score": 78,
        "reports": {
            "markdown": "# Express report",
            "html": "<!doctype html><html><body>Express report</body></html>",
            "pdf_base64": "JVBERi0xLjQK",
        },
        "progress": api._stage_progress("complete", "complete", "Complete"),
    }


def test_final_production_record_binding_survives_copied_legacy_marker(monkeypatch) -> None:
    store = MemoryAdapter()
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(hardening, "STORE", store)
    run_id = "express_run_final_terminal_binding"
    request = _request()

    def later_record_wrapper(run: str, payload: dict, response: dict) -> dict:
        stale = deepcopy(response)
        stale.update(
            {
                "status": "running",
                "current_stage": "truth_and_review_gates",
                "progress_percent": 94,
                "report_generation_status": "running",
                "worker_started": True,
            }
        )
        # Match the real express_async_api._record contract: return the outer
        # assessment storage record, whose nested response can still be stale.
        return store.put(
            "assessment_runs",
            run,
            {
                "workflow": "express",
                "run_id": run,
                "status": "running",
                "customer_id": payload["customer_id"],
                "project_id": payload["project_id"],
                "repository": payload["repository"],
                "request": deepcopy(payload),
                "response": stale,
                "payload": stale,
            },
        )

    # Reproduce a later wrapper that copied the old boolean marker with
    # functools.wraps even though it no longer executes the progress writer.
    setattr(later_record_wrapper, "_nico_express_progress_record_v1", True)
    monkeypatch.setattr(api, "_record", later_record_wrapper)

    def base_status(run: str, customer_id: str, project_id: str) -> dict:
        record = store.get("assessment_runs", run)
        assert isinstance(record, dict)
        assert record["customer_id"] == customer_id
        assert record["project_id"] == project_id
        return deepcopy(record["response"])

    monkeypatch.setattr(hardening, "_express_status_response", base_status)

    installed = install_express_status_liveness_patch()

    binding = installed["final_terminal_progress_record_binding"]
    assert binding["owner_verified"] is True
    assert binding["progress_source"] == "exact_record_argument_with_persisted_payload_fallback"
    assert getattr(api._record, _FINAL_RECORD_OWNER_MARKER, None) is api._record

    persisted = api._record(run_id, request, _terminal(run_id))
    assert persisted["status"] == "running"
    assert persisted["response"]["current_stage"] == "truth_and_review_gates"

    progress = store.get("express_run_progress", run_id)
    assert isinstance(progress, dict)
    assert progress["status"] == "complete"
    assert progress["current_stage"] == "complete"
    assert progress["progress_percent"] == 100
    assert progress["terminal_success_ready"] is True
    assert progress["report_formats_ready"] is True

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
    assert response["lifecycle_status"]["terminal_progress_source"] == "exact_record_argument_with_persisted_payload_fallback"
