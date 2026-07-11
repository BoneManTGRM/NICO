from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException

from nico import mid_assessment_api as api
from nico.api.production import REQUIRED_MID_ASSESSMENT_ROUTES, app, register_production_routes
from nico.mid_assessment_api import MidAssessmentRunRequest, MidAssessmentStatusRequest
from nico.mid_assessment_handlers import mid_assessment_handlers
from nico.mid_assessment_runs import (
    MID_ASSESSMENT_WORKFLOW,
    build_mid_status_payload,
    load_mid_assessment_run,
    persist_mid_assessment_run,
)
from nico.snapshot_assessment_handlers import (
    _snapshot_evidence_attachment_handler,
    _snapshot_scanner_handler,
)
from nico.storage import STORE


def _run_id() -> str:
    return f"midrun_{uuid4().hex[:16]}"


def _route_pairs(target: FastAPI) -> set[tuple[str, str]]:
    return {
        (str(method).upper(), str(getattr(route, "path", "")))
        for route in target.routes
        for method in (getattr(route, "methods", set()) or set())
    }


def _orchestrator_result(payload: dict, status: str = "running") -> dict:
    run_id = payload["run_id"]
    return {
        "status": status,
        "run_id": run_id,
        "repository": payload.get("repository") or payload.get("target") or "BoneManTGRM/NICO",
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "mode": payload.get("mode") or "mid",
        "progress": [
            {"step": "authorization", "status": "complete"},
            {
                "step": "repo_evidence",
                "status": "complete",
                "evidence": {
                    "snapshot_id": f"snapshot_{run_id}",
                    "repository_evidence_id": f"repo_evidence_{run_id}",
                    "complexity_evidence_id": f"complexity_evidence_{run_id}",
                },
            },
            {"step": "scanner_worker", "status": "queued" if status == "running" else "complete"},
            {"step": "evidence_attachment", "status": "pending" if status == "running" else "complete"},
            {"step": "scoring", "status": "planned" if status == "running" else "complete"},
            {"step": "reports", "status": "skipped"},
            {"step": "approval_request", "status": "skipped"},
        ],
        "scanner": {"scan_id": f"scan_{run_id}", "status": "queued" if status == "running" else "complete"},
        "scanner_evidence": {"status": "not_attached" if status == "running" else "attached", "scan_id": f"scan_{run_id}"},
        "assessment": {} if status == "running" else {"status": "draft", "run_id": run_id},
        "reports": {"markdown": "", "html": "", "pdf_base64": "", "pdf_filename": "nico-assessment.pdf", "pdf_error": ""},
        "approval": {"approval_id": "", "status": "not_requested"},
        "human_review_required": True,
        "client_ready": False,
        "generated_at": "2026-07-11T20:00:00Z",
    }


def _put_evidence(run_id: str) -> None:
    values = {
        f"snapshot_{run_id}": {"status": "attached", "snapshot_id": f"snapshot_{run_id}", "run_id": run_id, "repository": "BoneManTGRM/NICO", "commit_sha": "a" * 40},
        f"repo_evidence_{run_id}": {"status": "attached", "evidence_id": f"repo_evidence_{run_id}", "run_id": run_id, "snapshot_commit_sha": "a" * 40},
        f"complexity_evidence_{run_id}": {"status": "attached", "evidence_id": f"complexity_evidence_{run_id}", "run_id": run_id, "snapshot_commit_sha": "a" * 40},
    }
    for item_id, evidence in values.items():
        STORE.put("evidence_items", item_id, {
            "evidence_id": item_id,
            "customer_id": "customer_mid",
            "project_id": "project_mid",
            "run_id": run_id,
            "filename": f"{item_id}.json",
            "content_type": "application/json",
            "size_bytes": 1,
            "evidence": evidence,
        })


def test_mid_handler_composition_uses_snapshot_collection_and_evidence_bound_scoring():
    configured = mid_assessment_handlers(180)

    assert configured["scanner_worker"] is _snapshot_scanner_handler
    assert configured["evidence_attachment"] is _snapshot_evidence_attachment_handler
    assert callable(configured["repo_evidence"])
    assert callable(configured["scoring"])
    assert callable(configured["reports"])
    assert callable(configured["approval_request"])


def test_mid_run_creates_one_mid_identity_and_never_generates_express_report(monkeypatch):
    run_id = _run_id()
    _put_evidence(run_id)
    captured: dict = {}
    monkeypatch.setattr(api, "new_id", lambda prefix: run_id)

    def fake_orchestrator(payload, handlers):
        captured.update(payload)
        assert handlers["scanner_worker"] is _snapshot_scanner_handler
        return _orchestrator_result(payload)

    monkeypatch.setattr(api, "run_full_assessment_orchestration", fake_orchestrator)
    result = api.mid_assessment_response(MidAssessmentRunRequest(
        repository="https://github.com/BoneManTGRM/NICO",
        customer_id="customer_mid",
        project_id="project_mid",
        client_name="Example Client",
        project_name="Example Project",
        authorized_by="owner",
        authorization_confirmed=True,
    ))

    assert result["run_id"] == run_id
    assert result["assessment_type"] == "mid"
    assert result["service_tier"] == "mid"
    assert result["unified_run"] is True
    assert result["express_report_generated"] is False
    assert result["report_generation_status"] == "mid_report_pipeline_pending"
    assert result["repository_snapshot"]["commit_sha"] == "a" * 40
    assert result["repository_evidence"]["snapshot_commit_sha"] == "a" * 40
    assert result["complexity_evidence"]["snapshot_commit_sha"] == "a" * 40
    assert captured["run_id"] == run_id
    assert captured["mode"] == "mid"
    assert captured["build_reports"] is False
    assert captured["create_final_review_request"] is False
    assert result["reports"]["markdown"] == ""
    assert result["approval"]["status"] == "not_requested"

    stored = load_mid_assessment_run(run_id)
    assert stored is not None
    assert stored["workflow"] == MID_ASSESSMENT_WORKFLOW
    assert stored["service_tier"] == "mid"
    assert stored["scan_id"] == f"scan_{run_id}"
    assert stored["snapshot_id"] == f"snapshot_{run_id}"
    assert stored["snapshot_commit_sha"] == "a" * 40
    assert stored["request"]["build_reports"] is False
    assert stored["request"]["create_final_review_request"] is False


def test_mid_run_requires_authorization_and_uses_midrun_identity(monkeypatch):
    run_id = _run_id()
    monkeypatch.setattr(api, "new_id", lambda prefix: run_id)

    with pytest.raises(HTTPException) as exc_info:
        api.mid_assessment_response(MidAssessmentRunRequest(repository="BoneManTGRM/NICO", authorized_by="owner"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["assessment_type"] == "mid"
    assert exc_info.value.detail["run_id"] == run_id


def test_mid_status_restores_saved_scope_and_forces_mid_downstream_guardrails(monkeypatch):
    run_id = _run_id()
    initial = _orchestrator_result({
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_mid",
        "project_id": "project_mid",
        "mode": "mid",
    })
    persist_mid_assessment_run(initial, {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_mid",
        "project_id": "project_mid",
        "authorized_by": "owner",
        "authorization_confirmed": True,
        "mode": "mid",
        "build_reports": False,
        "create_final_review_request": False,
        "auto_continue": True,
    })
    _put_evidence(run_id)
    captured: dict = {}

    def fake_orchestrator(payload, handlers):
        captured.update(payload)
        return _orchestrator_result(payload, status="complete")

    monkeypatch.setattr(api, "run_full_assessment_orchestration", fake_orchestrator)
    monkeypatch.setattr(api, "plan_full_assessment_continuation", lambda payload, record, auto_continue: {
        "payload": dict(payload), "run_id": run_id, "scan_id": record.get("scan_id") or "", "scan": {"status": "complete"},
        "scan_status": "complete", "same_run": True, "auto_continue": auto_continue, "should_continue": True,
        "reuse_report": False, "reuse_approval": False, "request_review_from_existing_report": False,
        "report_id": "", "approval_id": "", "reason": "same-run scanner complete",
    })
    monkeypatch.setattr(api, "apply_full_assessment_continuation", lambda result, plan: result)

    result = api.mid_assessment_status_response(run_id, MidAssessmentStatusRequest())

    assert result["run_id"] == run_id
    assert result["status_refresh"] is True
    assert result["assessment_type"] == "mid"
    assert result["persistence"]["restored"] is True
    assert captured["repository"] == "BoneManTGRM/NICO"
    assert captured["customer_id"] == "customer_mid"
    assert captured["project_id"] == "project_mid"
    assert captured["mode"] == "mid"
    assert captured["build_reports"] is False
    assert captured["create_final_review_request"] is False


def test_mid_status_does_not_accept_non_mid_or_unknown_run_ids():
    with pytest.raises(HTTPException) as wrong_prefix:
        api.mid_assessment_status_response("fullrun_example", MidAssessmentStatusRequest())
    with pytest.raises(HTTPException) as missing:
        api.mid_assessment_status_response(_run_id(), MidAssessmentStatusRequest())
    assert wrong_prefix.value.status_code == 404
    assert missing.value.status_code == 404


def test_mid_persistence_rejects_non_mid_identity_and_other_workflow_collision():
    with pytest.raises(ValueError, match="midrun_ identity"):
        persist_mid_assessment_run({"run_id": "fullrun_wrong", "status": "running"}, {"run_id": "fullrun_wrong"})

    run_id = _run_id()
    STORE.put("assessment_runs", run_id, {
        "run_id": run_id,
        "customer_id": "customer",
        "project_id": "project",
        "workflow": "full_assessment",
        "status": "running",
    })
    with pytest.raises(ValueError, match="different workflow"):
        persist_mid_assessment_run({"run_id": run_id, "status": "running"}, {"run_id": run_id})


def test_mid_status_payload_reuses_saved_scanner_and_never_enables_reports():
    run_id = _run_id()
    persist_mid_assessment_run(_orchestrator_result({
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_mid",
        "project_id": "project_mid",
        "mode": "mid",
    }), {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_mid",
        "project_id": "project_mid",
        "authorization_confirmed": True,
        "build_reports": False,
        "create_final_review_request": False,
    })

    payload, record = build_mid_status_payload(run_id, {}, set())

    assert record is not None
    assert payload["run_id"] == run_id
    assert payload["scan_id"] == f"scan_{run_id}"
    assert payload["mode"] == "mid"
    assert payload["build_reports"] is False
    assert payload["create_final_review_request"] is False


def test_production_route_registration_is_complete_idempotent_and_distinct_from_legacy_mid():
    assert REQUIRED_MID_ASSESSMENT_ROUTES <= _route_pairs(app)
    assert ("POST", "/assessment/mid") in _route_pairs(app)
    target = FastAPI()
    register_production_routes(target)
    first = _route_pairs(target)
    register_production_routes(target)
    second = _route_pairs(target)
    assert REQUIRED_MID_ASSESSMENT_ROUTES <= first
    assert first == second
    for pair in REQUIRED_MID_ASSESSMENT_ROUTES:
        assert sum(1 for route in target.routes if getattr(route, "path", "") == pair[1] and pair[0] in (getattr(route, "methods", set()) or set())) == 1
