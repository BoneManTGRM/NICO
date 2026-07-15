from __future__ import annotations

import inspect

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import mid_assessment_api as api


def test_mid_live_progress_wrappers_preserve_request_model_signatures() -> None:
    start_signature = inspect.signature(api.mid_assessment_response)
    status_signature = inspect.signature(api.mid_assessment_status_response)

    assert start_signature.parameters["req"].annotation is api.MidAssessmentRunRequest
    assert status_signature.parameters["run_id"].annotation is str
    assert status_signature.parameters["req"].annotation is api.MidAssessmentStatusRequest


def test_registered_mid_status_route_accepts_json_body_with_scan_id() -> None:
    app = FastAPI()
    api.register_mid_assessment_routes(app)

    response = TestClient(app).post(
        "/assessment/mid-run/midrun_missing_wrapped_signature/status",
        json={
            "repository": "owner/repository",
            "scan_id": "scan_snapshot_wrapped_signature",
            "customer_id": "customer_signature",
            "project_id": "project_signature",
            "authorization_confirmed": True,
            "authorized": True,
            "auto_continue": False,
        },
    )

    assert response.status_code == 404
    assert response.status_code != 422
    assert response.json()["detail"]["status"] == "not_found"
