"""Synthetic software checks, never evidence of an owner's production approval."""
import base64
import hashlib
import io
import sqlite3
from copy import deepcopy
from functools import lru_cache

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from nico import comprehensive_operator_approval_v1 as subject
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import _review_projection, register_comprehensive_api_routes
from nico.comprehensive_review_decision_v1 import report_package_from_record, review_artifact_identity
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore
from tests.test_comprehensive_review_decision_v1 import _review_ready_record


@lru_cache(maxsize=1)
def fixture_record():
    from tests.test_phase4_approved_delivery_v4 import _record
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    record = _review_ready_record()
    package = report_package_from_record(record)
    assessment = report_package_from_record(_record())["json"]["assessment"]
    from tests.test_phase2_review_work_v1 import _register
    register = _register()
    template = assessment["canonical_scanner_finding_register"]["findings"][0]
    register["findings"] = [{**deepcopy(template), **finding} for finding in register["findings"]]
    register["totals"] = {"raw": 3, "approved_or_nonblocking": 0, "excluded_test_only": 0,
                          "material": 0, "review_required": 3, "exact_source": 0,
                          "source_path": 3, "payload_without_source": 0, "count_only": 0}
    package["json"]["assessment"]["canonical_scanner_finding_register"] = register
    provenance = deepcopy(assessment["nico_release_provenance"])
    provenance["assessment_run_id"] = record["identity"]["run_id"]
    provenance["assessed_repository_commit"] = record["identity"]["commit_sha"]
    package["json"]["assessment"]["nico_release_provenance"] = provenance
    record["stage_results"]["final_comprehensive_report_generation"]["report_package"] = rebuild_client_artifacts({"json": package["json"]})
    record["integrity_sha256"] = _record_hash(record)
    return record


@pytest.fixture
def service(tmp_path):
    record = deepcopy(fixture_record())
    store = ComprehensiveRunStore(lambda: sqlite3.connect(tmp_path / "runs.db"), dialect="sqlite")
    store.ensure_schema()
    store.create(record)
    return ComprehensiveRunService(store, {})


def payload(record, metadata=""):
    return dict(approval_kind="operator_report", decision="approved", review_authorized=True,
                authorization_confirmed=True, exact_report_acknowledged=True,
                reviewer=metadata, reviewer_role=metadata, decision_reason=metadata,
                expected_artifact_identity=review_artifact_identity(record))


def current(service):
    return service.load_read_only("comprun_review_en")


@pytest.mark.parametrize("metadata", ["", "TEST", "test", " TeSt ", "   "])
def test_optional_metadata_approves_exact_report_without_completing_specialist_work(service, metadata):
    before = current(service)
    original = deepcopy(before)
    disclosure = subject.review_disclosure(before)
    assert disclosure["status"] == "observed"
    assert disclosure["specialist_review_completed"] is False
    assert disclosure["remaining_candidate_count"] > 0
    assert disclosure["unresolved_high_impact_candidate_ids"]
    assert disclosure["quality_control_required_count"] > 0
    assert disclosure["quality_control_completed_count"] == 0
    approved = subject.approve_operator_report(service, before["identity"]["run_id"], payload(before, metadata))
    assert validate_comprehensive_run_record(approved)["status"] == "valid"
    edition = subject.validated_operator_edition(current(service))
    assert edition is not None
    for field in ("identity", "stage_results", "completed_stages", "status", "human_review_completed", "client_delivery_allowed"):
        assert approved[field] == original[field]
    assert approved.get("review_work_ledger") == original.get("review_work_ledger")
    assert approved.get("review_history") == original.get("review_history")
    assert "accepted_edition" not in approved
    assert "delivery_authorization" not in approved
    assert "approved_delivery_package" not in approved
    receipt = edition["review"]
    assert receipt["review_disclosure"] == disclosure
    assert receipt["source_review_artifact_identity"] == review_artifact_identity(original)
    assert receipt["source_identity"] == original["identity"]
    assert receipt["reviewer"] == (metadata.strip() or "Authenticated NICO operator")
    pdf = base64.b64decode(edition["reports"]["pdf_base64"], validate=True)
    assert hashlib.sha256(pdf).hexdigest() == edition["artifact_digests"]["pdf"]["sha256"]
    assert edition["reports"]["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    source_pdf = base64.b64decode(report_package_from_record(original)["pdf_base64"])
    assert hashlib.sha256(pdf).digest() != hashlib.sha256(source_pdf).digest()
    source_pages = PdfReader(io.BytesIO(source_pdf)).pages
    approved_pages = PdfReader(io.BytesIO(pdf)).pages
    assert [p.extract_text() for p in approved_pages[-len(source_pages):]] == [p.extract_text() for p in source_pages]
    cover = " ".join(" ".join(p.extract_text() for p in approved_pages[:-len(source_pages)]).split())
    assert "OPERATOR APPROVED FINAL" in cover
    assert "not" in cover.lower() and "specialist" in cover.lower()
    assert "BLOCKED" in cover
    assert receipt["source_review_artifact_identity"]["artifact_digests"]["pdf"]["sha256"] in cover
    response = _review_projection(ComprehensiveApiController(service)._response(approved, operation="reviewed", browser_projection=False), approved, operator_reports_authorized=True)
    assert response["operator_approval_status"] == "approved"
    assert response["approval_status"] == "operator_approved_final"
    assert response["human_review_completed"] is False
    assert response["client_delivery_allowed"] is False
    assert response["operator_approved_edition"] == edition
    with pytest.raises(ValueError):
        service.authorize_delivery(before["identity"]["run_id"], authorizer="TEST", authorizer_role="Security reviewer",
                                  authorization_reason="TEST", expected_artifact_identity=response["review_artifact_identity"])


@pytest.mark.parametrize("change", ["ack", "authorization", "revision", "run", "digest", "missing_pdf", "corrupt_pdf"])
def test_invalid_transitions_leave_no_approval(service, change):
    record = current(service)
    request = payload(record)
    if change == "ack": request["exact_report_acknowledged"] = False
    elif change == "authorization": request["authorization_confirmed"] = False
    elif change == "revision": request["expected_artifact_identity"]["revision"] -= 1
    elif change == "run": request["expected_artifact_identity"]["run_id"] = "another-run"
    elif change == "digest": request["expected_artifact_identity"]["report_artifact_digest"] = "0" * 64
    else:
        record["stage_results"]["final_comprehensive_report_generation"]["report_package"]["pdf_base64"] = "" if change == "missing_pdf" else base64.b64encode(b"corrupt").decode()
        record["integrity_sha256"] = _record_hash(record)
    with pytest.raises(ValueError): subject.build_operator_edition(record, request)
    assert "operator_approved_edition" not in current(service)


def test_duplicate_and_tampered_approvals_cannot_be_projected_as_current(service):
    record = current(service)
    request = payload(record)
    approved = subject.approve_operator_report(service, record["identity"]["run_id"], request)
    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        subject.approve_operator_report(service, record["identity"]["run_id"], request)
    assert current(service) == approved
    for field in ("pdf", "ledger", "source", "failed_stage"):
        damaged = deepcopy(approved)
        if field == "pdf": damaged["operator_approved_edition"]["reports"]["pdf_base64"] = base64.b64encode(b"%PDF damaged").decode()
        elif field == "ledger": damaged["review_work_ledger"] = {"changed": True}
        elif field == "source": damaged["identity"]["commit_sha"] = "b" * 40
        else: damaged["stage_results"]["final_comprehensive_report_generation"]["status"] = "failed"
        assert subject.validated_operator_edition(damaged) is None
        assert subject.project_operator_approval({}, damaged, include_reports=True)["operator_approval_status"].startswith("invalidated")


def test_api_authentication_and_acknowledgement_then_read_only_download(service, monkeypatch):
    # Exercise the real auth function with a synthetic test-only operator secret.
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "synthetic-test-operator-token")
    monkeypatch.setenv("NICO_ADMIN_WRITE_ENABLED", "true")
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=ComprehensiveApiController(service))
    client = TestClient(app)
    before = current(service)
    url = f'/assessment/comprehensive-run/{before["identity"]["run_id"]}/review'
    request = payload(before)
    assert client.post(url, json=request, headers={"x-nico-admin-token": "wrong"}).status_code == 403
    headers = {"x-nico-admin-token": "synthetic-test-operator-token"}
    read_url = url.removesuffix("/review")
    assert client.get(read_url, headers=headers).status_code == 200
    assert current(service) == before
    assert client.post(url, json={**request, "exact_report_acknowledged": False}, headers=headers).status_code >= 400
    response = client.post(url, json=request, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["operator_approval_status"] == "approved"
    persisted = current(service)
    retry = client.get(read_url, headers=headers)
    assert retry.status_code == 200
    assert retry.json()["operator_approved_edition"] == response.json()["operator_approved_edition"]
    assert current(service) == persisted
    assert retry.json()["client_delivery_allowed"] is False
    public = client.get(read_url)
    assert public.status_code == 200
    assert "operator_approved_edition" not in public.json()
    assert "OPERATOR-APPROVED-FINAL.pdf" not in public.text


def test_operator_source_and_localized_edition_have_independent_receipts(service):
    from nico import comprehensive_localized_edition_v1 as localized
    source = current(service)
    run_id = source["identity"]["run_id"]
    approved = subject.approve_operator_report(service, run_id, payload(source))
    source_edition = subject.validated_operator_edition(approved)
    _, entry, draft = localized.prepare_localized_edition(service, run_id, "es-MX", {
        "preparation_authorized": True, "authorization_confirmed": True,
        "expected_artifact_identity": subject.presented_operator_identity(approved, source_edition),
    })
    assert "operator_approved_edition" not in draft
    assert "source_operator_approval_sha256" in entry["parent_binding"]
    _, _, approved_locale = localized.mutate_localized_edition(service, run_id, "es-MX", payload(draft, "test"))
    locale_edition = subject.validated_operator_edition(approved_locale)
    assert locale_edition is not None
    assert locale_edition["review"]["source_identity"]["report_language"] == "es-MX"
    assert locale_edition["source_review_artifact_identity"] == review_artifact_identity(draft)
    assert locale_edition["review"]["review_disclosure"]["specialist_review_completed"] is False
    assert approved_locale["client_delivery_allowed"] is False
    assert "delivery_authorization" not in approved_locale
    assert subject.validated_operator_edition(current(service)) == source_edition
    _, _, readback = localized.read_localized_edition(service, run_id, "es-MX")
    assert subject.validated_operator_edition(readback) == locale_edition


def test_competing_writers_cannot_replace_first_receipt(service):
    from nico.comprehensive_run_store import ComprehensiveRunConflict
    original = current(service)
    request = payload(original)
    other_edition = subject.build_operator_edition(original, request)
    winner = subject.approve_operator_report(service, original["identity"]["run_id"], request)
    conflicting = deepcopy(original)
    conflicting["operator_approved_edition"] = other_edition
    conflicting["revision"] += 1
    conflicting["integrity_sha256"] = _record_hash(conflicting)
    with pytest.raises(ComprehensiveRunConflict):
        service._store.save(conflicting, expected_revision=original["revision"])
    assert current(service) == winner
