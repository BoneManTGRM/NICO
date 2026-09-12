"""Isolated authorization checks; these never authorize the owner's live report."""
import base64
import hashlib
import io
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_operator_approval_v1 import approve_operator_report, presented_operator_identity
from nico.comprehensive_operator_delivery_v1 import authorize_operator_delivery, validated_operator_delivery
from nico.comprehensive_operator_presentation_v1 import _render_source
from tests.test_comprehensive_operator_approval_v1 import service, current, payload


def approved_request(service, metadata=""):
    before = current(service)
    approved = approve_operator_report(service, before["identity"]["run_id"], payload(before))
    return approved, dict(delivery_kind="operator_report", delivery_authorized=True,
                         authorization_confirmed=True, authorizer=metadata, authorizer_role=metadata,
                         authorization_reason=metadata,
                         expected_artifact_identity=presented_operator_identity(approved, approved["operator_approved_edition"]))


@pytest.mark.parametrize("metadata", ["", "TEST", "test", " TeSt ", "   "])
def test_explicit_permission_persists_and_download_retains_source_and_work(service, metadata):
    approved, request = approved_request(service, metadata)
    run = approved["identity"]["run_id"]
    result = authorize_operator_delivery(service, run, request)
    assert result["client_delivery_allowed"] is True
    assert result["human_review_completed"] is False
    for key in ("identity", "stage_results", "operator_approved_edition", "review_work_ledger", "review_history"):
        assert result.get(key) == approved.get(key)
    edition = validated_operator_delivery(current(service))
    assert edition is not None
    assert result["revision"] == approved["revision"] + 1
    assert authorize_operator_delivery(service, run, request) == result
    receipt = edition["delivery_authorization"]
    assert receipt["authorized_artifact_identity"] == request["expected_artifact_identity"]
    assert receipt["transmission_performed"] is False
    pdf = base64.b64decode(edition["reports"]["pdf_base64"])
    assert hashlib.sha256(pdf).hexdigest() == edition["artifact_digests"]["pdf"]["sha256"]
    reader = PdfReader(io.BytesIO(pdf))
    assert "AUTHORIZ" in reader.pages[0].extract_text()
    assert "CLIENT-DELIVERY-AUTHORIZED.pdf" in edition["reports"]["pdf_filename"]
    for page in reader.pages:
        assert "CLIENT DELIVERY BLOCKED" not in page.extract_text()
    for field in ("pdf", "source", "receipt", "ledger"):
        damaged = deepcopy(result)
        if field == "pdf": damaged["operator_delivery_edition"]["reports"]["pdf_base64"] = base64.b64encode(b"%PDF bad").decode()
        elif field == "source": damaged["identity"]["commit_sha"] = "b" * 40
        elif field == "receipt": damaged["operator_delivery_edition"]["delivery_authorization"]["authorized_at"] = "changed"
        else: damaged["review_work_ledger"] = {"changed": True}
        assert validated_operator_delivery(damaged) is None


def test_api_rejects_missing_authority_stale_identity_and_false_success(service, monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "synthetic-test-operator-token")
    monkeypatch.setenv("NICO_ADMIN_WRITE_ENABLED", "true")
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=ComprehensiveApiController(service))
    client = TestClient(app)
    approved, request = approved_request(service)
    base = f'/assessment/comprehensive-run/{approved["identity"]["run_id"]}'
    headers = {"x-nico-admin-token": "synthetic-test-operator-token"}
    url = base + "/authorize-delivery"
    assert client.post(url, json=request, headers={"x-nico-admin-token": "wrong"}).status_code == 403
    for change in ({"authorization_confirmed": False}, {"delivery_authorized": False},
                   {"expected_artifact_identity": {**request["expected_artifact_identity"], "revision": 0}},
                   {"expected_artifact_identity": {**request["expected_artifact_identity"], "run_id": "other"}}):
        assert client.post(url, json={**request, **change}, headers=headers).status_code >= 400
        assert current(service) == approved
    response = client.post(url, json=request, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["client_delivery_allowed"] is True
    assert result["delivery_status"] == "authorized"
    assert result["human_review_completed"] is False
    persisted = current(service)
    read = client.get(base, headers=headers)
    assert read.status_code == 200, read.text
    assert read.json()["operator_approved_edition"] == result["operator_approved_edition"]
    assert current(service) == persisted
    assert client.post(url, json=request, headers=headers).json()["operator_approved_edition"] == result["operator_approved_edition"]
    assert current(service) == persisted
    public = client.get(base).json()
    assert "operator_approved_edition" not in public


@pytest.mark.parametrize("spanish", [False, True])
def test_blue_cover_updates_only_client_delivery_lifecycle(spanish):
    from reportlab.pdfgen import canvas
    output = io.BytesIO()
    c = canvas.Canvas(output)
    lines = (["Postura ejecutiva", "REVISIÓN HUMANA", "Pendiente", "ENTREGA AL CLIENTE", "Bloqueada"]
             if spanish else ["Executive posture", "HUMAN REVIEW", "Pending", "CLIENT DELIVERY", "Blocked"])
    lines += ["Technical finding: blocked dependency", "QC: Pending"]
    for n, line in enumerate(lines): c.drawString(20, 760 - n * 20, line)
    c.save()
    corrected, _ = _render_source(output.getvalue(), client_delivery_authorized=True)
    text = PdfReader(io.BytesIO(corrected)).pages[0].extract_text()
    assert ("Autorizada" if spanish else "Authorized") in text
    assert ("Aprobado" if spanish else "Approved") in text
    assert "Technical finding: blocked dependency" in text
    assert "QC: Pending" in text


def test_delivery_requires_prior_approval_and_locale_permission_stays_isolated(service):
    from nico import comprehensive_localized_edition_v1 as localized
    draft = current(service)
    with pytest.raises(ValueError, match="requires_current_operator_approval"):
        authorize_operator_delivery(service, draft["identity"]["run_id"], {
            "delivery_kind": "operator_report", "delivery_authorized": True,
            "authorization_confirmed": True, "expected_artifact_identity": {},
        })
    approved, _ = approved_request(service)
    run = approved["identity"]["run_id"]
    _, _, locale = localized.prepare_localized_edition(service, run, "es-MX", {
        "preparation_authorized": True, "authorization_confirmed": True,
        "expected_artifact_identity": presented_operator_identity(approved, approved["operator_approved_edition"]),
    })
    _, _, locale = localized.mutate_localized_edition(service, run, "es-MX", payload(locale))
    root_before = current(service)
    request = dict(delivery_kind="operator_report", delivery_authorized=True, authorization_confirmed=True,
                   expected_artifact_identity=presented_operator_identity(locale, locale["operator_approved_edition"]))
    _, _, released = localized.mutate_localized_edition(service, run, "es-MX", request, delivery=True)
    assert released["client_delivery_allowed"] is True
    assert released["human_review_completed"] is False
    _, _, readback = localized.read_localized_edition(service, run, "es-MX")
    assert validated_operator_delivery(readback) == validated_operator_delivery(released)
    assert current(service)["client_delivery_allowed"] is False
    for key in ("identity", "stage_results", "operator_approved_edition", "review_work_ledger"):
        assert current(service).get(key) == root_before.get(key)


def test_authorized_source_can_prepare_spanish_without_transferring_permission(service):
    from nico import comprehensive_localized_edition_v1 as localized
    from nico.comprehensive_operator_delivery_v1 import project_operator_delivery
    approved, request = approved_request(service)
    run = approved["identity"]["run_id"]
    authorized = authorize_operator_delivery(service, run, request)
    visible_identity = project_operator_delivery({}, authorized, include_reports=True)["review_artifact_identity"]
    root, _, draft = localized.prepare_localized_edition(service, run, "es-MX", {
        "preparation_authorized": True, "authorization_confirmed": True,
        "expected_artifact_identity": visible_identity,
    })
    assert root["client_delivery_allowed"] is True
    assert validated_operator_delivery(root) is not None
    assert draft["client_delivery_allowed"] is False
    assert "operator_delivery_edition" not in draft
    assert draft["human_review_completed"] is False
