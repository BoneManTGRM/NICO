from __future__ import annotations

import base64
import io
from types import SimpleNamespace

from pypdf import PdfReader

from nico import comprehensive_api_routes as routes
from nico.comprehensive_report_worker_runtime_v90 import (
    _native_report_base_v90,
    _report_identity,
)
from nico.comprehensive_run_record import create_comprehensive_run_record


CLIENT = "NICO Production Metadata Proof 2026-08-26"
PROJECT = "Comprehensive Metadata E2E Proof"
CONTACT = "NICO Metadata Proof Contact"
ACCESS = "Public GitHub repository via HTTPS/API — read-only production proof"
SCOPE = "BoneManTGRM/NICO — entire repository, current main branch — read-only production proof"


class _CapturingController:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        self.payload = payload
        return {
            "status": "ready",
            "run_id": str(payload["run_id"]),
            "repository": str(payload["repository"]),
            "commit_sha": str(payload["commit_sha"]),
            "evidence_ledger_id": str(payload["evidence_ledger_id"]),
            "customer_id": str(payload["customer_id"]),
            "project_id": str(payload["project_id"]),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }


def _request() -> SimpleNamespace:
    state = SimpleNamespace(
        comprehensive_runtime={
            "configured": True,
            "persistence_adapter": "postgres",
            "durability_verified": True,
            "survives_container_replacement_verified": True,
        }
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _browser_payload() -> dict[str, object]:
    return {
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_metadata_proof",
        "project_id": "project_metadata_proof",
        "client_name": CLIENT,
        "project_name": PROJECT,
        "authorized_by": "public_assessment_requester",
        "authorization_scope": "authorized defensive repository assessment",
        "authorization_confirmed": True,
        "authorized": True,
        "assessment_depth": "strategic",
        "report_language": "en",
        "human_evidence": {
            "stakeholder_context": {
                "evidence": {
                    "access_method": [ACCESS],
                    "primary_technical_contact": [CONTACT],
                    "authorized_scope": [SCOPE],
                },
                "reviewer": "",
                "observed_at": "",
                "source_reference": "",
                "excluded": False,
                "exclusion_rationale": "",
            }
        },
    }


def _final_report_context(record: dict[str, object]) -> dict[str, object]:
    identity = record["identity"]
    assert isinstance(identity, dict)
    return {
        "run_id": identity["run_id"],
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "evidence_ledger_id": identity["evidence_ledger_id"],
        "customer_id": identity["customer_id"],
        "project_id": identity["project_id"],
        "assessment_depth": identity["assessment_depth"],
        "report_language": identity["report_language"],
        "human_evidence": record["human_evidence"],
        "prior_stage_results": {},
    }


def test_ui_shaped_intake_metadata_survives_persistence_worker_and_final_artifacts(monkeypatch) -> None:
    """Regression for the production failure proven by comprun_55113db7ae674324923026d848a0039e.

    This intentionally starts with the same shape produced by the public UI instead of
    injecting display values at the report layer. It crosses canonical intake,
    normalization/persistence, detached-worker identity construction, and final report
    generation so a future upstream-only fix cannot create another false green.
    """

    controller = _CapturingController()
    monkeypatch.setattr(routes, "_controller", lambda _request: controller)
    monkeypatch.setattr(
        routes,
        "capture_repository_snapshot",
        lambda _payload: {"status": "attached", "commit_sha": "a" * 40},
    )
    monkeypatch.setattr(routes, "expected_commit_sha", lambda _payload: "")

    intake_response = routes._intake(_request(), _browser_payload())
    assert intake_response["human_review_required"] is True
    assert intake_response["client_delivery_allowed"] is False
    assert controller.payload is not None

    raw_human = controller.payload["human_evidence"]
    assert isinstance(raw_human, dict)
    raw_stakeholder = raw_human["stakeholder_context"]
    assert isinstance(raw_stakeholder, dict)
    raw_evidence = raw_stakeholder["evidence"]
    assert isinstance(raw_evidence, dict)
    assert raw_evidence["customer_name"] == CLIENT
    assert raw_evidence["project_name"] == PROJECT
    assert raw_evidence["primary_technical_contact"] == [CONTACT]
    assert raw_evidence["access_method"] == [ACCESS]
    assert raw_evidence["authorized_scope"] == [SCOPE]

    record = create_comprehensive_run_record(
        run_id=str(controller.payload["run_id"]),
        repository=str(controller.payload["repository"]),
        commit_sha=str(controller.payload["commit_sha"]),
        evidence_ledger_id=str(controller.payload["evidence_ledger_id"]),
        customer_id=str(controller.payload["customer_id"]),
        project_id=str(controller.payload["project_id"]),
        authorized=True,
        assessment_depth="strategic",
        report_language="en",
        human_evidence=raw_human,
    )

    modules = record["human_evidence"]["modules"]
    stakeholder = modules["stakeholder_context"]
    evidence = stakeholder["evidence"]
    assert evidence["customer_name"] == CLIENT
    assert evidence["project_name"] == PROJECT
    assert evidence["primary_technical_contact"] == [CONTACT]
    assert evidence["access_method"] == [ACCESS]
    assert evidence["authorized_scope"] == [SCOPE]

    context = _final_report_context(record)
    worker_identity = _report_identity(context)
    assert worker_identity["customer_name"] == CLIENT
    assert worker_identity["project_name"] == PROJECT
    assert worker_identity["primary_technical_contact"] == CONTACT

    final_stage = _native_report_base_v90(context, final=True)
    assert final_stage["status"] == "complete"
    assert final_stage["human_review_required"] is True
    assert final_stage["client_delivery_allowed"] is False

    report = final_stage["report_package"]
    canonical = report["json"]
    canonical_identity = canonical["identity"]
    assert canonical_identity["customer_id"] == "customer_metadata_proof"
    assert canonical_identity["project_id"] == "project_metadata_proof"
    assert canonical_identity["customer_name"] == CLIENT
    assert canonical_identity["project_name"] == PROJECT
    assert canonical_identity["primary_technical_contact"] == CONTACT

    markdown = str(report["markdown"])
    assert f"Client display name: {CLIENT}" in markdown
    assert f"Project display name: {PROJECT}" in markdown
    assert f"Primary technical contact: {CONTACT}" in markdown

    pdf_bytes = base64.b64decode(str(report["pdf_base64"]), validate=True)
    rendered = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf_bytes)).pages
    )
    assert CLIENT in rendered
    assert PROJECT in rendered

    # The professional client-evidence section must consume the same preserved canonical
    # identity, not reconstruct or infer it from repository ownership.
    import nico.comprehensive_report_review_integrity_v1 as integrity
    import nico.v2_premium_report_renderer as renderer

    integrity._install_required_report_sections()
    stages = renderer._canonical_stages(canonical)
    client_summary = next(
        item for item in stages if item.get("stage_id") == "client_evidence_summary"
    )
    retained = "\n".join(str(item) for item in client_summary.get("evidence") or [])
    assert f"Client display name: {CLIENT}" in retained
    assert f"Project display name: {PROJECT}" in retained
    assert f"Primary technical contact: {CONTACT}" in retained
