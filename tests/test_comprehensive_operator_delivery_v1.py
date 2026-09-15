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


@pytest.mark.parametrize("service", [False, True], indirect=True)
def test_source_version_preserves_old_authorized_bytes_and_binds_new_receipt_page(service, monkeypatch):
    from nico.comprehensive_review_decision_v1 import report_package_from_record
    from nico import comprehensive_operator_presentation_v1 as presentation
    approved, request = approved_request(service)
    result = authorize_operator_delivery(service, approved["identity"]["run_id"], request)
    edition = validated_operator_delivery(result)
    assert edition is not None
    source = report_package_from_record(result)["json"]
    receipt_bound = source.get("operator_approval_record_schema") == presentation.RECEIPT_VERSION
    if receipt_bound:
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(edition["reports"]["pdf_base64"]))).pages)
        assert "See certificate" not in text
        assert edition["reports"]["json"]["operator_approval_receipt"] == approved["operator_approved_edition"]["review"]
    else:
        assert "operator_approval_receipt" not in edition["reports"]["json"]
        def unexpected(*args, **kwargs):
            raise AssertionError("New receipt renderer must not affect historical identity")
        monkeypatch.setattr(presentation, "_approval_record_pdf", unexpected)
        presentation._render_source.cache_clear()
    assert validated_operator_delivery(current(service)) == edition
    assert authorize_operator_delivery(service, approved["identity"]["run_id"], request) == result


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


@pytest.mark.parametrize('spanish', [False, True])
def test_authorized_companions_use_receipts_not_stale_publication_labels(spanish):
    from nico.comprehensive_operator_report_formats import project_authorized_companion_formats
    from nico.comprehensive_four_phase_model_v1 import build_four_phase_program
    from nico.comprehensive_operator_approval_v1 import _cover
    # A reduced fixture; never a production approval or assessment.
    receipt = {'source_identity': {'report_language': 'es-MX' if spanish else 'en',
        'run_id': 'synthetic', 'commit_sha': 'a'*40},
        'source_review_artifact_identity': {'revision': 1, 'artifact_digests': {'pdf': {'sha256': 'b'*64}}},
        'reviewer': 'Fixture operator', 'reviewer_role': 'Fixture', 'decided_at': '2026-01-01T00:00:00Z',
        'reason': 'Fixture only', 'review_disclosure': {'status': 'unknown'},
        'approval_certificate_sha256': 'c'*64}
    delivery = {'authorizer': 'Fixture operator', 'authorized_at': '2026-01-01T00:01:00Z',
        'delivery_authorization_certificate_sha256': 'd'*64}
    canonical = {'identity': receipt['source_identity'], 'human_report_export_schema': 'nico.human_report_export.v1',
        'operator_approval_status': 'approved', 'client_delivery_allowed': True, 'human_review_completed': False}
    canonical['four_phase_program'] = build_four_phase_program(canonical)
    _, certificate = _cover(receipt, spanish=spanish)
    phase = 'Programa de evaluación en cuatro fases' if spanish else 'Four-Phase Assessment Program'
    boundary = 'Límite de decisión' if spanish else 'Decision Boundary'
    gate = 'Puerta de revisión humana y aceptación' if spanish else 'Human Review and Acceptance Gate'
    literal = '<span data-nico-client-literal="true">CLIENT DELIVERY BLOCKED; supplied claim only</span>'
    instruction = ('- [ ] Aprobar o rechazar este borrador automatizado antes de la entrega.' if spanish else
        '- [ ] Approve or reject this immutable automated draft before delivery.')
    reports = {'json': canonical, 'pdf_base64': 'unchanged-final-pdf',
        'markdown': certificate + '\n\n---\n\n# Report\n\n## ' + phase + '\nold phase\n\n## ' + boundary +
        '\nHuman review is required. Client delivery is blocked.\n\n## ' + gate + '\n' + instruction +
        '\n- [ ] Pending specialist QC\n\n## Human Review Checklist\n- [ ] Approve or reject the exact immutable report package before any client delivery.\n\n## Evidence\n- ' + literal + '\n', 'html': '<p>old</p>'}
    original = deepcopy(reports)
    project_authorized_companion_formats(reports, receipt=receipt, delivery=delivery)
    for kind in ('markdown', 'html'):
        assert 'Client delivery remains BLOCKED' not in reports[kind]
        assert 'La entrega al cliente sigue BLOQUEADA' not in reports[kind]
        assert instruction not in reports[kind]
        assert 'old phase' not in reports[kind]
        assert 'Approve or reject the exact immutable' not in reports[kind]
        assert literal in reports[kind]
        assert 'Pending specialist QC' in reports[kind]
        assert delivery['delivery_authorization_certificate_sha256'] in reports[kind]
        assert ('AUTORIZADA' if spanish else 'AUTHORIZED') in reports[kind]
    assert reports['pdf_base64'] == original['pdf_base64']
    assert reports['json'] == original['json']
    once = deepcopy(reports)
    project_authorized_companion_formats(reports, receipt=receipt, delivery=delivery)
    assert reports == once


@pytest.mark.parametrize('service', [True], indirect=True)
def test_companion_presentation_preserves_retained_authority_and_pdf_on_retry(service):
    from nico.comprehensive_operator_delivery_v1 import project_operator_delivery
    approved, request = approved_request(service)
    result = authorize_operator_delivery(service, approved['identity']['run_id'], request)
    retained = deepcopy(result['operator_delivery_edition'])
    visible = project_operator_delivery({}, result, include_reports=True)
    assert visible['operator_approved_edition']['reports']['pdf_base64'] == retained['reports']['pdf_base64']
    assert visible['operator_approved_edition']['review'] == retained['review']
    assert visible['operator_approved_edition']['delivery_authorization'] == retained['delivery_authorization']
    assert current(service) == result
    assert authorize_operator_delivery(service, approved['identity']['run_id'], request) == result
    assert project_operator_delivery({}, current(service), include_reports=True) == visible
    assert 'retained_operator_delivery_edition' not in project_operator_delivery({}, result, include_reports=False)


@pytest.mark.parametrize('service', [True], indirect=True)
def test_old_delivery_keeps_original_binding_in_versioned_read_only_export(service, monkeypatch):
    from nico import comprehensive_operator_report_formats as formats
    from nico.comprehensive_operator_delivery_v1 import project_operator_delivery, render_delivery_companion_presentation
    from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
    approved, request = approved_request(service)
    with monkeypatch.context() as context:
        context.setattr(formats, 'project_authorized_companion_formats', lambda *args, **kwargs: None)
        old_record = authorize_operator_delivery(service, approved['identity']['run_id'], request)
    original = deepcopy(old_record)
    visible = project_operator_delivery({}, old_record, include_reports=True)
    retained = visible['retained_operator_delivery_edition']
    corrected = visible['operator_approved_edition']
    assert retained == old_record['operator_delivery_edition']
    assert corrected['reports']['json'] == retained['reports']['json']
    assert corrected['reports']['pdf_base64'] == retained['reports']['pdf_base64']
    assert corrected['review'] == retained['review']
    assert corrected['delivery_authorization'] == retained['delivery_authorization']
    assert corrected['rendering_derivation']['authoritative_delivery_manifest_sha256'] == retained['accepted_edition_manifest_sha256']
    for edition in (retained, corrected):
        body = deepcopy(edition); claimed = body.pop('accepted_edition_manifest_sha256')
        assert canonical_sha256(body) == claimed
    assert render_delivery_companion_presentation(corrected) == corrected
    assert project_operator_delivery({}, current(service), include_reports=True) == visible
    assert authorize_operator_delivery(service, approved['identity']['run_id'], request) == original
    assert current(service) == original
    for field in ('review', 'reports', 'delivery_authorization'):
        damaged = deepcopy(original)
        damaged['operator_delivery_edition'][field]['tampered'] = True
        assert project_operator_delivery({}, damaged, include_reports=True)['client_delivery_allowed'] is False
