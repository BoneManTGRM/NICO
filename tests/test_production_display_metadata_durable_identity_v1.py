from __future__ import annotations

import sqlite3
from pathlib import Path


def test_controller_persists_display_identity_without_mutating_scope_ids(tmp_path) -> None:
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.comprehensive_run_record import _record_hash

    database = tmp_path / "display-identity.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    service = ComprehensiveRunService(store, {})
    controller = ComprehensiveApiController(service)

    response = controller.start(
        {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_display_identity_proof",
            "evidence_ledger_id": "ledger_display_identity_proof",
            "customer_id": "canonical_customer_scope",
            "project_id": "canonical_project_scope",
            "client_name": "  NICO Acceptance Client  ",
            "project_name": "  NICO Acceptance Project  ",
            "assessment_depth": "strategic",
            "report_language": "es-MX",
            "human_evidence": {
                "modules": {
                    "stakeholder_context": {
                        "evidence": {
                            "access_method": ["GitHub HTTPS/API - read-only"],
                            "primary_technical_contact": ["NICO Acceptance Contact"],
                            "authorized_scope": [
                                "Full repository at exact assessed SHA - read-only"
                            ],
                        }
                    }
                }
            },
            "authorized": True,
            "authorization_confirmed": True,
        }
    )

    assert response["customer_id"] == "canonical_customer_scope"
    assert response["project_id"] == "canonical_project_scope"
    assert response["customer_name"] == "NICO Acceptance Client"
    assert response["project_name"] == "NICO Acceptance Project"

    persisted = store.load(response["run_id"])
    identity = persisted["identity"]
    assert identity["customer_id"] == "canonical_customer_scope"
    assert identity["project_id"] == "canonical_project_scope"
    assert identity["customer_name"] == "NICO Acceptance Client"
    assert identity["project_name"] == "NICO Acceptance Project"
    assert persisted["integrity_sha256"] == _record_hash(persisted)


def test_display_identity_is_carried_into_stage_context(tmp_path) -> None:
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore

    database = tmp_path / "stage-context.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    seen: dict[str, object] = {}

    def capture(context):
        seen.update(context)
        return {"status": "complete"}

    service = ComprehensiveRunService(store, {"authorization_and_scope": capture})
    record = service.start(
        run_id="comprun_stage_context_proof",
        repository="BoneManTGRM/NICO",
        commit_sha="b" * 40,
        evidence_ledger_id="ledger_stage_context_proof",
        customer_id="canonical_customer_scope",
        project_id="canonical_project_scope",
        customer_name="NICO Acceptance Client",
        project_name="NICO Acceptance Project",
        authorized=True,
        assessment_depth="strategic",
        report_language="en",
    )
    service.resume(record["identity"]["run_id"], max_stages=1)
    assert seen["customer_id"] == "canonical_customer_scope"
    assert seen["project_id"] == "canonical_project_scope"
    assert seen["customer_name"] == "NICO Acceptance Client"
    assert seen["project_name"] == "NICO Acceptance Project"


def test_production_proof_asserts_and_retains_actual_browser_intake_payload() -> None:
    source = Path("scripts/spanish_comprehensive_live_acceptance_v3.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        'intake_payload.get("client_name") == PROOF_CLIENT_NAME',
        'intake_payload.get("project_name") == PROOF_PROJECT_NAME',
        '("access_method", PROOF_ACCESS_METHOD)',
        '("primary_technical_contact", PROOF_PRIMARY_TECHNICAL_CONTACT)',
        '("authorized_scope", PROOF_AUTHORIZED_SCOPE)',
        '"browser_intake_payload_verified": True',
        '"browser_intake_payload": sanitized_intake_payload',
    ):
        assert marker in source
