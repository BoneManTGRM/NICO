from __future__ import annotations

import base64
import hashlib
import io
import json
import sqlite3
from types import SimpleNamespace

import pytest
from pypdf import PdfReader


EXACT_LITERAL_FIXTURES = (
    {
        "client_name": "Cody Jenkins",
        "project_name": "NICO Audit",
        "primary_technical_contact": "Cody — Repository owner / project lead",
        "access_method": (
            "Public GitHub repository via HTTPS/API — read-only access"
        ),
        "authorized_scope": (
            "BoneManTGRM/NICO — entire repository, current main branch. "
            "Read-only technical and security assessment."
        ),
    },
    {
        "client_name": "Compañía Águila, S.A. de C.V.",
        "project_name": "Proyecto Ñandú / Release 2.0",
        "primary_technical_contact": "María-José Pérez - CTO / Ingeniería",
        "access_method": "GitHub Enterprise - acceso de solo lectura",
        "authorized_scope": (
            "organizacion/proyecto - rama release/2026.08; código, "
            "configuración y CI/CD."
        ),
    },
)


def _browser_shaped_human_evidence(
    authorized_scope: str = "Full repository at exact assessed SHA - read-only",
) -> dict[str, object]:
    return {
        "stakeholder_context": {
            "evidence": {
                "access_method": ["GitHub HTTPS/API - read-only"],
                "primary_technical_contact": ["NICO Acceptance Contact"],
                "authorized_scope": [authorized_scope],
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

    authorized_scope = "Scope start — " + ("ñ /.- " * 260) + "— scope end"
    assert 1200 < len(authorized_scope) < 4000
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
            "human_evidence": _browser_shaped_human_evidence(authorized_scope),
            "engagement_field_states": {
                "client_name": {"state": "supplied_unverified"},
                "project_name": {"state": "supplied_unverified"},
                "primary_technical_contact": {"state": "supplied_unverified"},
                "access_method": {"state": "supplied_unverified"},
                "authorized_scope": {"state": "supplied_unverified"},
            },
        },
    )

    record = store.load(str(response["run_id"]))
    engagement = record["engagement_metadata"]
    assert verify_comprehensive_engagement_metadata(engagement) is True
    assert engagement["client_name"] == "NICO Acceptance Client"
    assert engagement["project_name"] == "NICO Acceptance Project"
    assert engagement["primary_technical_contact"] == "NICO Acceptance Contact"
    assert engagement["access_method"] == "GitHub HTTPS/API - read-only"
    assert engagement["authorized_scope"] == authorized_scope
    assert {
        field: record["state"]
        for field, record in engagement["field_states"].items()
    } == {
        "client_name": "supplied_unverified",
        "project_name": "supplied_unverified",
        "primary_technical_contact": "supplied_unverified",
        "access_method": "supplied_unverified",
        "authorized_scope": "supplied_unverified",
    }

    # Canonical partitioning identity remains separate from descriptive engagement data.
    assert record["identity"]["customer_id"] == "customer_scope_regression"
    assert record["identity"]["project_id"] == "project_scope_regression"
    assert validate_comprehensive_run_record(record)["status"] == "valid"

    # Status/recovery exposes the exact durable snapshot so production proof can verify
    # persistence directly rather than inferring it from a later PDF.
    projected = controller.status(str(response["run_id"]))
    assert projected["engagement_metadata"] == engagement
    assert projected["record"]["engagement_metadata"] == engagement
    assert projected["engagement_metadata"]["authorized_scope"] == authorized_scope
    assert not projected["engagement_metadata"]["authorized_scope"].endswith("…")

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
    assert seen["authorized_scope"] == authorized_scope

    report_identity = _report_identity(seen)
    assert report_identity["customer_id"] == "customer_scope_regression"
    assert report_identity["project_id"] == "project_scope_regression"
    assert report_identity["customer_name"] == "NICO Acceptance Client"
    assert report_identity["project_name"] == "NICO Acceptance Project"
    assert (
        report_identity["primary_technical_contact"]
        == "NICO Acceptance Contact"
    )


def test_real_intake_persists_and_recovers_explicit_exclusions(tmp_path) -> None:
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore

    database = tmp_path / "durable-engagement-exclusions.sqlite3"

    def connect():
        return sqlite3.connect(database)

    store = ComprehensiveRunStore(connect)
    store.ensure_schema()
    controller = ComprehensiveApiController(ComprehensiveRunService(store, {}))
    response = controller.start(
        {
            "run_id": "comprun_explicit_exclusion_persistence",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_explicit_exclusion_persistence",
            "customer_id": "customer_explicit_exclusion",
            "project_id": "project_explicit_exclusion",
            "client_name": "Cody Jenkins",
            "project_name": "NICO Audit",
            "assessment_depth": "strategic",
            "report_language": "es-MX",
            "authorized": True,
            "authorization_confirmed": True,
            "human_evidence": {
                "stakeholder_context": {
                    "evidence": {},
                    "excluded": True,
                    "exclusion_rationale": "Excluded by the requester.",
                }
            },
            "engagement_field_states": {
                "client_name": {"state": "supplied_unverified"},
                "project_name": {"state": "supplied_unverified"},
                "primary_technical_contact": {
                    "state": "excluded_from_scope",
                    "source": "user_action",
                },
                "access_method": {
                    "state": "excluded_from_scope",
                    "source": "user_action",
                },
                "authorized_scope": {
                    "state": "excluded_from_scope",
                    "source": "user_action",
                },
            },
        }
    )

    run_id = str(response["run_id"])
    persisted = store.load(run_id)
    recovered = controller.status(run_id)
    for projection in (
        persisted["engagement_metadata"],
        recovered["engagement_metadata"],
        recovered["record"]["engagement_metadata"],
    ):
        assert projection["client_name"] == "Cody Jenkins"
        assert projection["project_name"] == "NICO Audit"
        for field in (
            "primary_technical_contact",
            "access_method",
            "authorized_scope",
        ):
            assert projection[field] == ""
            assert projection["field_states"][field] == {
                "state": "excluded_from_scope",
                "value": None,
                "source": "user_action",
                "reason": "Excluded by the requester.",
            }


@pytest.mark.parametrize("fixture", EXACT_LITERAL_FIXTURES)
def test_exact_literals_survive_api_persistence_recovery_and_every_report_format(
    tmp_path,
    fixture: dict[str, str],
) -> None:
    from nico import comprehensive_report_package as report_package
    from nico import comprehensive_report_review_integrity_v1 as report_integrity
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_decision_grade_csv_v6 import _evidence_csv
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore

    database = tmp_path / "literal-round-trip.sqlite3"

    def connect():
        return sqlite3.connect(database)

    store = ComprehensiveRunStore(connect)
    store.ensure_schema()
    controller = ComprehensiveApiController(ComprehensiveRunService(store, {}))
    fixture_id = hashlib.sha256(
        json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    run_id = "comprun_exact_literal_" + fixture_id
    response = controller.start(
        {
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "c" * 40,
            "evidence_ledger_id": "ledger_" + run_id,
            "customer_id": "customer_exact_literal",
            "project_id": "project_exact_literal",
            "client_name": fixture["client_name"],
            "project_name": fixture["project_name"],
            "assessment_depth": "strategic",
            "report_language": "en",
            "authorized": True,
            "authorization_confirmed": True,
            "human_evidence": {
                "stakeholder_context": {
                    "evidence": {
                        "primary_technical_contact": [
                            fixture["primary_technical_contact"]
                        ],
                        "access_method": [fixture["access_method"]],
                        "authorized_scope": [fixture["authorized_scope"]],
                    }
                }
            },
            "engagement_field_states": {
                field: {"state": "supplied_unverified"}
                for field in fixture
            },
        }
    )

    persisted = store.load(str(response["run_id"]))
    recovered = controller.status(str(response["run_id"]))
    metadata = recovered["engagement_metadata"]
    assert persisted["engagement_metadata"] == metadata
    assert recovered["record"]["engagement_metadata"] == metadata
    for field, literal in fixture.items():
        assert metadata[field] == literal
        assert metadata["field_states"][field] == {
            "state": "supplied_unverified",
            "value": literal,
            "source": "client_supplied_intake",
        }

    report_integrity._install_required_report_sections()
    for language in ("en", "es-MX"):
        canonical = {
            "report_language": language,
            "locale": language,
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": "c" * 40,
                "run_id": run_id,
                "report_language": language,
                "customer_name": fixture["client_name"],
                "project_name": fixture["project_name"],
                "primary_technical_contact": fixture[
                    "primary_technical_contact"
                ],
                "access_method": fixture["access_method"],
                "authorized_scope": fixture["authorized_scope"],
            },
            "engagement_metadata": metadata,
            "assessment": {
                "technical_score": 93,
                "canonical_evidence_adjusted_score": 93,
                "maturity_signal": {"score": 93, "presented_score": 93},
                "sections": [],
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "scanner_execution_records": [],
            "review_candidate_summary": {},
            "technical_triage": {"workload_metrics": {}},
            "stage_summaries": [],
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        stages = renderer._canonical_stages(canonical)
        markdown = report_package._markdown(
            canonical["identity"],
            canonical["assessment"],
            stages,
            "2026-08-31T00:00:00Z",
        )
        rendered_html = report_package._semantic_html(
            markdown,
            "NICO Comprehensive",
        )
        evidence_csv = _evidence_csv(stages)
        canonical_json = json.dumps(canonical, ensure_ascii=False)
        encoded_pdf, error, page_count = report_package._pdf(
            canonical["identity"],
            canonical["assessment"],
            stages,
            "2026-08-31T00:00:00Z",
        )
        assert error is None
        assert page_count > 0
        pdf_text = " ".join(
            "\n".join(
                page.extract_text() or ""
                for page in PdfReader(
                    io.BytesIO(base64.b64decode(encoded_pdf))
                ).pages
            ).split()
        )
        for literal in fixture.values():
            assert literal in canonical_json
            assert literal in evidence_csv
            assert literal in markdown
            assert literal in rendered_html
            assert " ".join(literal.split()) in pdf_text
        for state in metadata["field_states"].values():
            assert state["state"] == "supplied_unverified"
            assert '"state": "supplied_unverified"' in canonical_json


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
