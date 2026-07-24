from __future__ import annotations

import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.final_review_operator_api as operator


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")
    app = FastAPI()

    @app.post("/reports/final-review/{approval_id}/{state}")
    def legacy_transition(approval_id: str, state: str):
        return {"approval_id": approval_id, "state": state}

    operator.register_final_review_operator_routes(app)
    return TestClient(app)


def test_operator_routes_require_admin_token(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/operations/final-review/express/run_1")

    assert response.status_code == 403
    assert response.json()["detail"]["status"] == "blocked"


def test_legacy_final_review_write_is_also_admin_gated(monkeypatch) -> None:
    client = _client(monkeypatch)

    blocked = client.post("/reports/final-review/approval_1/approved")
    allowed = client.post(
        "/reports/final-review/approval_1/approved",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert blocked.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["state"] == "approved"


def test_operator_status_supports_express_and_comprehensive(monkeypatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        operator,
        "_review_status",
        lambda service, run_id, customer_id, project_id: {
            "status": "ok",
            "service": service,
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
        },
    )

    express = client.get(
        "/operations/final-review/express/express_run_1?customer_id=c1&project_id=p1",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )
    comprehensive = client.get(
        "/operations/final-review/comprehensive/comprun_1?customer_id=c2&project_id=p2",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert express.status_code == 200
    assert express.json()["service"] == "express"
    assert comprehensive.status_code == 200
    assert comprehensive.json()["service"] == "comprehensive"


def test_operator_review_requires_supported_service(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get(
        "/operations/final-review/mid/midrun_1",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert response.status_code == 400
    assert "express or comprehensive" in response.json()["detail"]["message"]


def test_operator_transition_requires_reviewer_note_for_rejection(monkeypatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        operator,
        "_transition_review",
        lambda service, approval_id, state, actor, note: {
            "status": "ok",
            "service": service,
            "approval_id": approval_id,
            "state": state,
            "actor": actor,
            "note": note,
        },
    )

    response = client.post(
        "/operations/final-review/express/approval_1/rejected",
        headers={"X-NICO-Admin-Token": "operator-secret"},
        json={"actor": "Reviewer", "note": "Evidence is incomplete."},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "rejected"
    assert response.json()["actor"] == "Reviewer"


def test_operator_approved_pdf_download_returns_exact_pdf(monkeypatch) -> None:
    client = _client(monkeypatch)
    pdf = b"%PDF-1.4\n% exact approved report\n"
    monkeypatch.setattr(
        operator,
        "_approved_pdf_artifact",
        lambda service, run_id, customer_id, project_id: {
            "client_delivery_allowed": True,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_filename": "nico-approved.pdf",
            "pdf_sha256": "a" * 64,
        },
    )

    response = client.get(
        "/operations/final-review/comprehensive/comprun_1/approved-pdf?customer_id=c1&project_id=p1",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert response.status_code == 200
    assert response.content == pdf
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="nico-approved.pdf"'
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["x-nico-run-id"] == "comprun_1"
    assert response.headers["x-nico-pdf-sha256"] == "a" * 64


def test_operator_approved_pdf_download_is_admin_gated(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/operations/final-review/express/express_run_1/approved-pdf")

    assert response.status_code == 403
    assert response.json()["detail"]["status"] == "blocked"


def test_operator_approved_pdf_download_fails_closed_on_invalid_pdf(monkeypatch) -> None:
    client = _client(monkeypatch)
    monkeypatch.setattr(
        operator,
        "_approved_pdf_artifact",
        lambda service, run_id, customer_id, project_id: {
            "client_delivery_allowed": True,
            "pdf_base64": base64.b64encode(b"not-a-pdf").decode("ascii"),
        },
    )

    response = client.get(
        "/operations/final-review/express/express_run_1/approved-pdf",
        headers={"X-NICO-Admin-Token": "operator-secret"},
    )

    assert response.status_code == 409
    assert "PDF integrity validation" in response.json()["detail"]["message"]


def test_express_approved_pdf_lookup_uses_approved_same_run_record(monkeypatch) -> None:
    expected = {"client_delivery_allowed": True, "pdf_base64": "encoded"}
    monkeypatch.setattr(
        operator,
        "client_acceptance_status",
        lambda run_id, customer_id, project_id: {
            "approvals": [
                {"status": "pending", "approved_delivery": {}},
                {"status": "approved", "approved_delivery": expected},
            ]
        },
    )

    artifact = operator._approved_pdf_artifact("express", "express_run_1", "c1", "p1")

    assert artifact is expected


def test_comprehensive_approved_pdf_lookup_reads_full_report_artifact(monkeypatch) -> None:
    expected = {"client_delivery_allowed": True, "pdf_base64": "encoded"}
    monkeypatch.setattr(
        operator,
        "final_review_status",
        lambda run_id, customer_id, project_id: {
            "approvals": [{"status": "approved", "report_id": "report_1"}]
        },
    )
    monkeypatch.setattr(
        operator,
        "get_report",
        lambda report_id: {"report_id": report_id, "approved_delivery": expected},
    )

    artifact = operator._approved_pdf_artifact("comprehensive", "comprun_1", "c1", "p1")

    assert artifact is expected
