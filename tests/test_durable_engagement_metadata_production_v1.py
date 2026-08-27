from __future__ import annotations

import sqlite3
from types import SimpleNamespace


def _browser_shaped_human_evidence() -> dict[str, object]:
    return {
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


def test_real_intake_persists_first_class_engagement_metadata_from_mobile_shape(
    tmp_path,
    monkeypatch,
) -> None:
    from nico import comprehensive_api_routes as routes
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_engagement_metadata_v1 import (
        verify_comprehensive_engagement_metadata,
    )
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    from nico.comprehensive_report_worker_runtime_v90 import _report_identity
    from nico.comprehensive_run_record import validate_comprehensive_run_record
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore

    database = tmp_path / "durable-engagement-metadata.sqlite3"

    def connect():
        return sqlite3.connect(database)

    store = ComprehensiveRunStore(connect)
    store.ensure_schema()
    service = ComprehensiveRunService(store, {})
    controller = ComprehensiveApiController(service)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                comprehensive_api_controller=controller,
                comprehensive_runtime={
                    "configured": True,
                    "persistence_adapter": "sqlite",
                    "durability_verified": True,
                    "survives_container_replacement_verified": True,
                },
            )
        )
    )

    monkeypatch.setattr(
        routes,
        "capture_repository_snapshot",
        lambda _payload: {
            "status": "attached",
            "commit_sha": "a" * 40,
        },
    )
    monkeypatch.setattr(routes, "expected_commit_sha", lambda _payload: "")

    response = routes._intake(
        request,
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_scope_regression",
            "project_id": "project_scope_regression",
            "client_name": "NICO Acceptance Client",
            "project_name": "NICO Acceptance Project",
            "assessment_depth": "strategic",
            "report_language": "es-MX",
            "authorized": True,
            "authorization_confirmed": True,
            "human_evidence": _browser_shaped_human_evidence(),
        },
    )

    record = store.load(str(response["run_id"]))
    engagement = record["engagement_metadata"]
    assert verify_comprehensive_engagement_metadata(engagement) is True
    assert engagement["client_name"] == "NICO Acceptance Client"
    assert engagement["project_name"] == "NICO Acceptance Project"
    assert engagement["primary_technical_contact"] == "NICO Acceptance Contact"
    assert engagement["access_method"] == "GitHub HTTPS/API - read-only"
    assert (
        engagement["authorized_scope"]
        == "Full repository at exact assessed SHA - read-only"
    )

    # Canonical partitioning identity remains separate from descriptive engagement data.
    assert record["identity"]["customer_id"] == "customer_scope_regression"
    assert record["identity"]["project_id"] == "project_scope_regression"
    assert validate_comprehensive_run_record(record)["status"] == "valid"

    # Status/recovery exposes the exact durable snapshot so production proof can verify
    # persistence directly rather than inferring it from a later PDF.
    projected = controller.status(str(response["run_id"]))
    assert projected["engagement_metadata"] == engagement
    assert projected["record"]["engagement_metadata"] == engagement

    # Exercise the same stage-context builder used by final report generation. The
    # browser-shaped arrays have already been normalized to singular exact values before
    # this boundary and no ContextVar or request object is available here.
    seen: dict[str, object] = {}
    first_stage = COMPREHENSIVE_STAGES[0]

    def capture_stage(context):
        seen.update(context)
        return {
            "status": "complete",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "commit_sha": context["commit_sha"],
            "evidence_ledger_id": context["evidence_ledger_id"],
        }

    service._stage_executors = {first_stage: capture_stage}
    service._run_next_stage(record)
    persisted_after_stage = store.load(str(response["run_id"]))
    assert persisted_after_stage["engagement_metadata"] == engagement
    assert validate_comprehensive_run_record(persisted_after_stage)["status"] == "valid"

    assert seen["engagement_metadata"] == engagement
    assert seen["customer_name"] == "NICO Acceptance Client"
    assert seen["project_name"] == "NICO Acceptance Project"
    assert seen["primary_technical_contact"] == "NICO Acceptance Contact"
    assert seen["access_method"] == "GitHub HTTPS/API - read-only"
    assert (
        seen["authorized_scope"]
        == "Full repository at exact assessed SHA - read-only"
    )

    report_identity = _report_identity(seen)
    assert report_identity["customer_id"] == "customer_scope_regression"
    assert report_identity["project_id"] == "project_scope_regression"
    assert report_identity["customer_name"] == "NICO Acceptance Client"
    assert report_identity["project_name"] == "NICO Acceptance Project"
    assert (
        report_identity["primary_technical_contact"]
        == "NICO Acceptance Contact"
    )


def test_engagement_metadata_never_infers_missing_fields() -> None:
    from nico.comprehensive_engagement_metadata_v1 import (
        build_comprehensive_engagement_metadata,
        verify_comprehensive_engagement_metadata,
    )

    engagement = build_comprehensive_engagement_metadata(
        client_name="",
        project_name="",
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "access_method": ["Public repository"],
                    "authorized_scope": ["Read-only repository scope"],
                }
            }
        },
    )
    assert verify_comprehensive_engagement_metadata(engagement) is True
    assert engagement["client_name"] == ""
    assert engagement["project_name"] == ""
    assert engagement["primary_technical_contact"] == ""
    assert engagement["access_method"] == "Public repository"
    assert engagement["authorized_scope"] == "Read-only repository scope"
    assert engagement["repository_inference_prohibited"] is True
    assert engagement["directly_scored"] is False
