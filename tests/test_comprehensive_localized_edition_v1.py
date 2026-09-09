"""Synthetic software fixtures, never professional review evidence."""
from copy import deepcopy
import base64
import hashlib
import io
import json
from pypdf import PdfReader

import pytest

from nico import comprehensive_localized_edition_v1 as subject
from nico.comprehensive_review_decision_v1 import review_artifact_identity, report_package_from_record
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_record import _record_hash
from tests.test_comprehensive_review_decision_v1 import _review_ready_record, _MemoryStore


def _review(record):
    return dict(reviewer="SYNTHETIC SOFTWARE-TEST INFORMATION — NOT PROFESSIONAL JUDGMENT",
                reviewer_role="Security reviewer", decision="approved",
                decision_reason="SYNTHETIC SOFTWARE-TEST exact-edition approval",
                expected_artifact_identity=review_artifact_identity(record))


@pytest.fixture
def source(monkeypatch):
    from nico import comprehensive_run_service as service_module, comprehensive_api_routes as routes
    from nico.comprehensive_approved_delivery_v4 import attach_approved_delivery_package, validate_approved_delivery_package
    from tests.test_phase4_approved_delivery_v4 import _record as provenance_fixture
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    record = _review_ready_record()
    package = report_package_from_record(record)
    phase4_assessment = report_package_from_record(provenance_fixture())["json"]["assessment"]
    provenance = deepcopy(phase4_assessment["nico_release_provenance"])
    provenance["assessment_run_id"] = record["identity"]["run_id"]
    provenance["assessed_repository_commit"] = record["identity"]["commit_sha"]
    package["json"]["assessment"]["nico_release_provenance"] = provenance
    package["json"]["assessment"]["canonical_scanner_finding_register"] = deepcopy(phase4_assessment["canonical_scanner_finding_register"])
    record["stage_results"]["final_comprehensive_report_generation"]["report_package"] = rebuild_client_artifacts({"json": package["json"]})
    record["integrity_sha256"] = _record_hash(record)
    # Bind the same v4 builder/validator pair installed by production bootstrap.
    monkeypatch.setattr(service_module, "attach_approved_delivery_package", attach_approved_delivery_package)
    monkeypatch.setattr(routes, "validate_approved_delivery_package", validate_approved_delivery_package)
    service = ComprehensiveRunService(_MemoryStore(record), {})
    record = service.review_work(record["identity"]["run_id"], {
        "action": "disposition_candidate", "candidate_id": "candidate-phase4-1",
        "disposition": "false_positive", "rationale": "SYNTHETIC SOFTWARE-TEST INFORMATION — fixture non-actionable candidate; NOT PROFESSIONAL JUDGMENT",
        "reviewer": "SYNTHETIC SOFTWARE-TEST reviewer", "reviewer_role": "Security reviewer",
        "review_authorized": True, "authorization_confirmed": True,
    })
    service.review(record["identity"]["run_id"], **_review(record))
    return service


def _prepare(service):
    root = deepcopy(service._store.record)
    return subject.prepare_localized_edition(service, root["identity"]["run_id"], "es-MX", {
        "preparation_authorized": True, "authorization_confirmed": True,
        "expected_artifact_identity": review_artifact_identity(root),
    })


def test_separate_retained_locale_approval_preserves_source_and_delivery_boundary(source):
    original = deepcopy(source._store.record)
    root, entry, draft = _prepare(source)
    assert draft["status"] == "review_required"
    assert draft["client_delivery_allowed"] is False
    assert entry["report_language"] == "es-MX"
    assert draft["identity"]["run_id"] == original["identity"]["run_id"]
    assert draft["identity"]["commit_sha"] == original["identity"]["commit_sha"]
    assert report_package_from_record(draft)["json"]["identity"]["report_language"] == "es-MX"
    retained = deepcopy(entry)
    _, repeated, _ = _prepare(source)
    assert repeated == retained
    payload = {**_review(draft), "review_authorized": True, "authorization_confirmed": True}
    _, approved_entry, approved = subject.mutate_localized_edition(source, draft["identity"]["run_id"], "es-MX", payload)
    assert approved["status"] == "approved"
    assert approved["accepted_edition"]["report_language"] == "es-MX"
    approved_report = report_package_from_record(approved)
    approved_text = " ".join(" ".join(page.extract_text() or "" for page in PdfReader(
        io.BytesIO(base64.b64decode(approved_report["pdf_base64"]))
    ).pages).casefold().split())
    for stale in ("estado de revisión: aprobación humana pendiente", "la aprobación humana autorizada sigue pendiente", "entrega al cliente permanece bloqueada"):
        assert stale not in approved_text
    assert approved["client_delivery_allowed"] is False
    assert "delivery_authorization" not in approved
    assert approved_entry["parent_binding"] == retained["parent_binding"]
    for key in ("identity", "stage_results", "accepted_edition", "review_history", "client_delivery_allowed"):
        assert source._store.record[key] == original[key]
    # Exercise serialization/restart readback rather than reusing an in-memory object.
    source._store.record = json.loads(json.dumps(source._store.record))
    _, _, readback = subject.read_localized_edition(source, draft["identity"]["run_id"], "es-MX")
    assert report_package_from_record(readback) == report_package_from_record(approved)
    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        subject.mutate_localized_edition(source, draft["identity"]["run_id"], "es-MX", payload)
    delivery = {"delivery_authorized": True, "authorization_confirmed": True,
                "authorizer": "SYNTHETIC SOFTWARE-TEST delivery authorization",
                "authorizer_role": "Security reviewer", "authorization_reason": "SYNTHETIC SOFTWARE-TEST protected package only",
                "expected_artifact_identity": review_artifact_identity(approved)}
    with pytest.raises(ValueError, match="explicit_delivery_authorization_required"):
        subject.mutate_localized_edition(source, draft["identity"]["run_id"], "es-MX", {**delivery, "delivery_authorized": False}, delivery=True)
    _, _, delivered = subject.mutate_localized_edition(source, draft["identity"]["run_id"], "es-MX", delivery, delivery=True)
    assert delivered["client_delivery_allowed"] is True
    assert report_package_from_record(delivered) == report_package_from_record(approved)
    assert delivered["accepted_edition"] == approved["accepted_edition"]
    archive = delivered["approved_delivery_package"]
    assert hashlib.sha256(base64.b64decode(archive["zip_base64"])).hexdigest() == archive["zip_sha256"]
    assert source._store.record["client_delivery_allowed"] is False
    assert source._store.record["accepted_edition"] == original["accepted_edition"]
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_api_routes import _review_projection
    projected = _review_projection(ComprehensiveApiController(source)._response(
        delivered, operation="delivery_authorized", browser_projection=False,
    ), delivered)
    assert projected["approval_status"] == "approved_final"
    assert projected["client_delivery_allowed"] is True
    assert projected["review_artifact_identity"] == review_artifact_identity(delivered)
    source_current = source.load(original["identity"]["run_id"])
    source_delivered = source.authorize_delivery(
        original["identity"]["run_id"], authorizer=delivery["authorizer"],
        authorizer_role=delivery["authorizer_role"], authorization_reason=delivery["authorization_reason"],
        expected_artifact_identity=review_artifact_identity(source_current),
    )
    assert source_delivered["client_delivery_allowed"] is True
    assert source_delivered["accepted_edition"] == original["accepted_edition"]
    _, _, still_delivered = subject.read_localized_edition(source, original["identity"]["run_id"], "es-MX")
    assert still_delivered["client_delivery_allowed"] is True
    assert report_package_from_record(still_delivered) == report_package_from_record(delivered)


def test_source_required_no_implicit_approval_and_tampering_rejected(source):
    root = source._store.record
    run_id = root["identity"]["run_id"]
    with pytest.raises(KeyError, match="localized_edition_not_prepared"):
        subject.read_localized_edition(source, run_id, "es-MX")
    with pytest.raises(ValueError, match="explicit_localized_preparation"):
        subject.prepare_localized_edition(source, run_id, "es-MX", {})
    with pytest.raises(ValueError, match="localized_edition_use_source_controls"):
        subject.read_localized_edition(source, run_id, "en")
    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        subject.prepare_localized_edition(source, run_id, "es-MX", {
            "preparation_authorized": True, "authorization_confirmed": True,
            "expected_artifact_identity": {**review_artifact_identity(root), "revision": 0},
        })
    _prepare(source)
    pristine = deepcopy(source._store.record)
    entry = source._store.record["localized_editions"]["es-MX"]
    entry["parent_binding"]["source_report_artifact_digest"] = "0" * 64
    entry["integrity_sha256"] = subject._entry_hash(entry)
    source._store.record["integrity_sha256"] = _record_hash(source._store.record)
    with pytest.raises(ValueError, match="localized_edition_source_binding_changed"):
        subject.read_localized_edition(source, run_id, "es-MX")
    source._store.record = pristine
    source._store.record["localized_editions"]["es-MX"]["report_package"]["markdown"] += "tampered"
    source._store.record["integrity_sha256"] = _record_hash(source._store.record)
    with pytest.raises(ValueError, match="localized_edition_integrity_invalid"):
        subject.read_localized_edition(source, run_id, "es-MX")


def test_unapproved_source_cannot_prepare():
    record = _review_ready_record()
    service = ComprehensiveRunService(_MemoryStore(record), {})
    with pytest.raises(ValueError, match="localized_edition_requires_approved_source"):
        _prepare(service)


def test_every_localized_route_authorizes_before_access(monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from nico import comprehensive_api_routes as routes
    app = FastAPI()
    subject.register_localized_edition_routes(app)
    subject.register_localized_edition_routes(app)
    def deny(token):
        raise HTTPException(403, detail="denied")
    monkeypatch.setattr(routes, "_authorize_review", deny)
    def unexpected(request):
        raise AssertionError("unauthorized route accessed controller")
    monkeypatch.setattr(routes, "_controller", unexpected)
    client = TestClient(app)
    base = subject.ROUTE.format(run_id="does-not-exist", report_language="es-MX")
    for method, path in (("GET", base), ("POST", base), ("POST", base + "/review"),
                         ("POST", base + "/authorize-delivery"), ("GET", base + "/approved-delivery-package")):
        assert client.request(method, path).status_code == 403


def test_completed_product_review_and_qc_carry_into_localized_approval():
    from tests.test_phase2_final_decision_delivery_truth_v3 import _record as candidate_fixture
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_review_work_safe_v1 import review_work_projection
    record = _review_ready_record()
    package = report_package_from_record(record)
    fixture_package = report_package_from_record(candidate_fixture())
    package["json"]["assessment"]["canonical_scanner_finding_register"] = deepcopy(
        fixture_package["json"]["assessment"]["canonical_scanner_finding_register"]
    )
    register = package["json"]["assessment"]["canonical_scanner_finding_register"]
    register["totals"] = {"raw": 1, "review_required": 1, "source_path": 1}
    register["summary_by_category"] = {"security": deepcopy(register["totals"])}
    package = rebuild_client_artifacts({"json": package["json"]})
    record["stage_results"]["final_comprehensive_report_generation"]["report_package"] = package
    record["integrity_sha256"] = _record_hash(record)
    service = ComprehensiveRunService(_MemoryStore(record), {})
    run_id = record["identity"]["run_id"]
    def action(kind, **fields):
        return service.review_work(run_id, {
            "action": kind, "reviewer": "SYNTHETIC SOFTWARE-TEST reviewer A",
            "reviewer_role": "SYNTHETIC SOFTWARE-TEST ROLE", "review_authorized": True,
            "authorization_confirmed": True, **fields,
        })
    current = action("configure_qc_sampling", sampling_strategy="risk_weighted", sample_size=1)
    current = action("disposition_candidate", candidate_id="candidate-final-1", disposition="false_positive",
                     rationale="SYNTHETIC SOFTWARE-TEST INFORMATION — fixture non-actionable retained candidate; NOT PROFESSIONAL JUDGMENT")
    assert review_work_projection(current)["ready_for_final_approval"] is False
    with pytest.raises(ValueError):
        service.review(run_id, **_review(current))
    current = action("quality_control", reviewer="SYNTHETIC SOFTWARE-TEST QC B",
                     candidate_id="candidate-final-1", qc_outcome="agree",
                     qc_note="SYNTHETIC SOFTWARE-TEST QC — NOT INDEPENDENT PROFESSIONAL QC; fixture evidence/disposition consistent")
    assert review_work_projection(current)["ready_for_final_approval"] is True
    # A subsequent supported disposition changes its binding and makes old QC stale.
    current = action("disposition_candidate", candidate_id="candidate-final-1", disposition="not_applicable",
                     rationale="SYNTHETIC SOFTWARE-TEST revised fixture disposition; NOT PROFESSIONAL JUDGMENT")
    assert review_work_projection(current)["ready_for_final_approval"] is False
    with pytest.raises(ValueError):
        service.review(run_id, **_review(current))
    current = action("quality_control", reviewer="SYNTHETIC SOFTWARE-TEST QC B",
                     candidate_id="candidate-final-1", qc_outcome="agree",
                     qc_note="SYNTHETIC SOFTWARE-TEST QC — NOT INDEPENDENT PROFESSIONAL QC; agrees with revised fixture disposition")
    approved_source = service.review(run_id, **_review(current))
    _, _, draft = _prepare(service)
    projection = review_work_projection(draft)
    assert projection["ready_for_final_approval"] is True
    assert projection["quality_control_completed_count"] == 1
    assert draft["review_work_ledger"] == approved_source["review_work_ledger"]
    _, _, approved = subject.mutate_localized_edition(service, run_id, "es-MX", {
        **_review(draft), "review_authorized": True, "authorization_confirmed": True,
    })
    assert approved["status"] == "approved"
    assert approved["accepted_edition"]["review_work_ledger_sha256"] == approved_source["accepted_edition"]["review_work_ledger_sha256"]
    assert approved["review_work_ledger"] == approved_source["review_work_ledger"]
    assert service._store.record["stage_results"] == approved_source["stage_results"]


def test_zero_candidate_source_ledger_remains_numeric_and_bound():
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    record = _review_ready_record()
    package = report_package_from_record(record)
    package["json"]["assessment"]["canonical_scanner_finding_register"] = {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_record_count": 0, "findings": [], "review_workload_clusters": [],
        "totals": {"raw": 0}, "summary_by_category": {},
        "technical_triage": {"total_candidates": 0, "triaged_candidates": 0},
    }
    record["stage_results"]["final_comprehensive_report_generation"]["report_package"] = rebuild_client_artifacts({"json": package["json"]})
    record["integrity_sha256"] = _record_hash(record)
    service = ComprehensiveRunService(_MemoryStore(record), {})
    run_id = record["identity"]["run_id"]
    approved_source = service.review(run_id, **_review(record))
    assert approved_source["review_work_ledger"]["candidate_count"] == 0
    _, _, draft = _prepare(service)
    assert draft["review_work_ledger"] == approved_source["review_work_ledger"]
    _, _, approved = subject.mutate_localized_edition(service, run_id, "es-MX", {
        **_review(draft), "review_authorized": True, "authorization_confirmed": True,
    })
    assert approved["status"] == "approved"
    assert approved["review_work_ledger"] == approved_source["review_work_ledger"]
    assert approved["review_work_ledger"]["candidate_count"] == 0
    assert service._store.record["accepted_edition"] == approved_source["accepted_edition"]
