from __future__ import annotations

import base64
import io
import json
import zipfile
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache

import pytest

import nico.comprehensive_run_service as run_service_module

from nico.comprehensive_approved_delivery_v4 import (
    _json_bytes,
    _sha256,
    _zip,
    attach_approved_delivery_package,
    bind_phase4_approval_manifest,
    validate_approved_delivery_package,
)
from nico.comprehensive_automated_delivery_v1 import build_automated_delivery_package
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_delivery_authorization_v1 import (
    authorize_accepted_edition,
    validate_delivery_authorization,
)
from nico.comprehensive_review_decision_v1 import (
    build_reviewed_edition,
    review_artifact_identity,
)
from nico.comprehensive_review_work_safe_v1 import apply_review_work_action
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts


def _pdf() -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    document.drawString(72, 720, "NICO Comprehensive Phase 4 exact reviewed analysis")
    document.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@lru_cache(maxsize=1)
def _record_template() -> dict:
    identity = {
        "run_id": "comprun_phase4_delivery",
        "repository": "OutsideOrg/python-service",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_phase4_delivery",
        "customer_id": "customer-phase4",
        "client_id": "client-phase4",
        "project_id": "project-phase4",
        "workspace_id": "workspace-phase4",
        "tenant_id": "tenant-phase4",
        "assessment_depth": "comprehensive",
        "report_language": "en",
        "generated_at": "2026-08-21T13:00:00Z",
    }
    finding = {
        "candidate_id": "candidate-phase4-1",
        "finding_id": "finding-phase4-1",
        "cluster_id": "cluster-phase4-1",
        "severity": "low",
        "scanner": "bandit",
        "category": "security",
        "rule": "fixture-rule",
        "path": "src/app.py",
        "candidate_lineage_version": "nico.candidate_lineage.v1",
        "lineage": {"version": "nico.candidate_lineage.v1", "status": "newly_observed"},
        "technical_triage_verdict": "not_actionable",
        "technical_triage_confidence": 0.99,
        "technical_triage": {
            "version": "nico.technical_triage.v1",
            "verdict": "not_actionable",
            "confidence": 0.99,
        },
        "evidence_change_state": "new",
        "grouped_review_eligible": False,
        "review_requires_individual_attention": False,
        "homogeneous_evidence": True,
        "homogeneous_verdict": True,
        "review_routing_class": "AUTOMATED_TRIAGE_COMPLETE",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    register = {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_lineage_version": "nico.candidate_lineage.v1",
        "candidate_record_count": 1,
        "findings": [finding],
        "review_workload_clusters": [
            {
                "cluster_id": "cluster-phase4-1",
                "candidate_ids": ["candidate-phase4-1"],
                "candidate_record_count": 1,
                "cluster_size": 1,
                "representative_candidate_id": "candidate-phase4-1",
                "grouped_review_eligible": False,
                "grouped_human_review_cluster": False,
                "homogeneous_evidence": True,
                "homogeneous_verdict": True,
                "underlying_candidate_disposition_required": True,
            }
        ],
        "technical_triage": {
            "version": "nico.technical_triage.v1",
            "total_candidates": 1,
            "triaged_candidates": 1,
        },
        "totals": {
            "raw": 1,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
            "material": 0,
            "review_required": 1,
            "exact_source": 0,
            "source_path": 1,
            "payload_without_source": 0,
            "count_only": 0,
        },
        "scanner_versions": {"bandit": "1.9.0"},
    }
    canonical = {
        "product_name": "NICO Comprehensive",
        "identity": {
            key: identity[key]
            for key in (
                "run_id",
                "repository",
                "commit_sha",
                "evidence_ledger_id",
                "report_language",
                "assessment_depth",
                "customer_id",
                "project_id",
                "generated_at",
            )
        },
        "generated_at": identity["generated_at"],
        "report_language": "en",
        "assessment_depth": "comprehensive",
        "assessment": {"canonical_scanner_finding_register": register},
        "findings_register": [],
        "roadmap": [],
        "staffing_plan": [],
        "generator_versions": {
            "nico_backend_build_commit": "b" * 40,
            "frontend_build_commit": "c" * 40,
            "assessment_engine_version": "nico.engine.v1",
            "scoring_model_version": "nico.score.v1",
            "report_renderer_version": "nico.renderer.v1",
            "artifact_generation_version": "nico.artifacts.v1",
            "candidate_lineage_version": "nico.candidate_lineage.v1",
            "technical_triage_version": "nico.technical_triage.v1",
            "scanner_versions": {"bandit": "1.9.0"},
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package = {
        "report_id": "report-phase4-delivery",
        "product_name": "NICO Comprehensive",
        "package_classification": "client_final",
        "report_language": "en",
        "markdown": "# NICO Comprehensive\n\nDRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n",
        "html": "<html><body><main><article><h1>NICO Comprehensive</h1></article></main></body></html>",
        "pdf_base64": _pdf(),
        "pdf_page_count": 1,
        "json": canonical,
        "canonical_truth_sha256": "evidence-bundle-phase4",
        "findings_csv": "finding_id,title\nfixture,Fixture\n",
        "evidence_csv": "evidence_id,source\nev-1,scanner\n",
        "jira_csv": "summary,description\nFixture,Remediation fixture\n",
        "candidate_register_csv": "candidate_id,disposition\ncandidate-phase4-1,false_positive\n",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package = rebuild_client_artifacts(package)
    return {
        "identity": identity,
        "status": "review_required",
        "terminal": True,
        "revision": 1,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "completed_stages": list(COMPREHENSIVE_STAGES),
        "human_evidence": {
            "modules": {
                "stakeholder_context": {
                    "evidence": {
                        "engagement_mode": ["client"],
                        "client_identity": ["Acme Holdings"],
                        "project_identity": ["Python service review"],
                        "repository_identity": [identity["repository"]],
                        "primary_technical_contact": ["security@example.test"],
                        "access_method": ["GitHub App read-only access"],
                        "authorized_scope": ["Entire repository at immutable commit"],
                        "authorization_confirmation": ["confirmed"],
                    }
                }
            }
        },
        "stage_results": {
            "immutable_repository_snapshot": {
                "snapshot": {"tree_sha": "d" * 40, "commit_sha": identity["commit_sha"]}
            },
            "deep_scanner_triage": {"scanner_run_id": "scan-phase4"},
            "final_comprehensive_report_generation": {
                "status": "complete",
                "report_package": package,
            },
        },
        "generator_versions": canonical["generator_versions"],
    }


def _record() -> dict:
    return deepcopy(_record_template())


def _reviewed_record() -> dict:
    record = _record()
    ledger = apply_review_work_action(
        record,
        {
            "action": "disposition_candidate",
            "candidate_id": "candidate-phase4-1",
            "disposition": "false_positive",
            "rationale": "Exact retained evidence supports a non-actionable human disposition.",
            "reviewer": "Alice Security",
            "reviewer_role": "Cybersecurity specialist",
            "review_authorized": True,
            "authorization_confirmed": True,
        },
        now=datetime(2026, 8, 21, 14, 0, tzinfo=UTC),
    )
    record["review_work_ledger"] = ledger
    return record


def _approved_pending_authorization() -> tuple[dict, dict]:
    decision_record = _reviewed_record()
    manifest = build_reviewed_edition(
        decision_record,
        reviewer="Alice Security",
        reviewer_role="Cybersecurity specialist",
        decision="approved",
        decision_reason="All exact candidate and residual-risk review gates are complete.",
        decided_at="2026-08-21T15:00:00+00:00",
    )
    decision_record["status"] = "approved"
    decision_record["human_review_completed"] = True
    decision_record["accepted_edition"] = deepcopy(manifest)
    decision_record["review_decision"] = deepcopy(manifest)
    decision_record["review_history"] = [deepcopy(manifest)]
    return decision_record, manifest


def _decision_and_manifest() -> tuple[dict, dict]:
    decision_record, manifest = _approved_pending_authorization()
    decision_record["delivery_authorization"] = authorize_accepted_edition(
        decision_record,
        manifest,
        authorizer="Alice Security",
        authorizer_role="Cybersecurity specialist",
        authorization_reason="Explicitly authorize delivery of this exact accepted edition.",
        authorized_at="2026-08-21T15:05:00+00:00",
        expected_artifact_identity=review_artifact_identity(decision_record),
    )
    return decision_record, manifest


def _fully_rehash_archive(
    delivery: dict,
    *,
    entry_changes: dict[str, bytes] | None = None,
    manifest_changes: dict | None = None,
) -> dict:
    output = deepcopy(delivery)
    with zipfile.ZipFile(
        io.BytesIO(base64.b64decode(output["zip_base64"], validate=True)),
        "r",
    ) as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    entries.update(entry_changes or {})
    manifest = deepcopy(output["manifest"])
    manifest.update(manifest_changes or {})
    for row in manifest["artifacts"]:
        content = entries[row["path"]]
        row["sha256"] = _sha256(content)
        row["size_bytes"] = len(content)
    manifest_bytes = _json_bytes(manifest)
    entries["11_evidence_manifest.json"] = manifest_bytes
    archive = _zip(entries)
    output["manifest"] = manifest
    output["zip_base64"] = base64.b64encode(archive).decode("ascii")
    output["zip_sha256"] = _sha256(archive)
    output["zip_size_bytes"] = len(archive)
    output["artifact_count"] = len(manifest["artifacts"])
    certificate = output["certificate"]
    certificate["evidence_manifest_sha256"] = _sha256(manifest_bytes)
    certificate["delivery_package_sha256"] = _sha256(archive)
    certificate["delivery_package_size_bytes"] = len(archive)
    certificate.pop("delivery_authorization_certificate_sha256", None)
    certificate["delivery_authorization_certificate_sha256"] = canonical_sha256(
        certificate
    )
    return output


def test_phase4_approved_delivery_binds_full_identity_and_receipt_inside_one_report_package() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = attached["approved_delivery_package"]
    receipt = delivery["phase4_approval_receipt"]
    certificate = delivery["certificate"]

    assert attached["accepted_edition"] == manifest
    assert attached["accepted_edition"]["accepted_edition_manifest_sha256"] == manifest[
        "accepted_edition_manifest_sha256"
    ]
    assert receipt["client_identity"] == "Acme Holdings"
    assert receipt["project_identity"] == "Python service review"
    assert receipt["assessment_run_id"] == "comprun_phase4_delivery"
    assert receipt["repository"] == "OutsideOrg/python-service"
    assert receipt["assessed_repository_commit"] == "a" * 40
    assert receipt["review"]["authorization_basis"] == "protected_admin_write_and_explicit_review_authorization"
    assert receipt["review"]["automation_may_not_approve"] is True
    assert certificate["phase4_approval_receipt_sha256"] == receipt["approval_receipt_sha256"]
    assert certificate["client_identity"] == "Acme Holdings"
    assert certificate["project_identity"] == "Python service review"
    assert delivery["one_client_report"] is True
    assert delivery["client_pdf_count"] == 1

    archive = base64.b64decode(delivery["zip_base64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as zipped:
        pdf_names = [name for name in zipped.namelist() if name.endswith(".pdf")]
        assert pdf_names == ["01_nico_comprehensive_report.pdf"]
        authorized_pdf = zipped.read("01_nico_comprehensive_report.pdf")
        from pypdf import PdfReader

        authorized_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(io.BytesIO(authorized_pdf)).pages
        )
        assert "CLIENT DELIVERY AUTHORIZED" in authorized_text
        assert "Delivery: Authorized" in authorized_text
        assert "DELIVERY CONTROLLED" not in authorized_text.upper()
        assert _sha256(authorized_pdf) == certificate["authorized_edition_pdf_sha256"]
        assert certificate["approved_source_pdf_sha256"] == receipt["pdf_sha256"]
        assert "12_phase4_approval_receipt.json" in zipped.namelist()
        assert "16_delivery_authorization.json" in zipped.namelist()
        assert "11_evidence_manifest.json" in zipped.namelist()
        assert zipped.read("15_approval_record.json") == _json_bytes(manifest)
        assert zipped.read("16_delivery_authorization.json") == _json_bytes(
            attached["delivery_authorization"]
        )

    assert attached["integrity_sha256"] != receipt["version_truth"][
        "mutable_operational_history_reference"
    ]
    validation = validate_approved_delivery_package(attached, delivery)
    assert validation["status"] == "valid"
    assert validation["validation_errors"] == []


def test_delivery_authorization_keeps_accepted_edition_byte_for_byte_immutable() -> None:
    record, manifest = _approved_pending_authorization()
    before = _json_bytes(manifest)
    before_hash = manifest["accepted_edition_manifest_sha256"]

    authorization = authorize_accepted_edition(
        record,
        manifest,
        authorizer="Alice Security",
        authorizer_role="Cybersecurity specialist",
        authorization_reason="Explicit client delivery authorization.",
        authorized_at="2026-08-21T15:05:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )
    record["delivery_authorization"] = authorization
    attached = attach_approved_delivery_package(record, manifest)

    assert _json_bytes(attached["accepted_edition"]) == before
    assert attached["accepted_edition"]["accepted_edition_manifest_sha256"] == before_hash
    assert authorization["accepted_edition_manifest_sha256"] == before_hash
    assert "delivery_authorization" not in attached["accepted_edition"]
    assert attached["approved_delivery_package"]["authorized_edition_created"] is True
    assert attached["approved_delivery_package"]["approved_report_pdf_preserved_exactly"] is False
    assert attached["approved_delivery_package"]["approved_source_pdf_sha256"] == manifest[
        "artifact_digests"
    ]["pdf"]["sha256"]


def test_service_authorization_is_distinct_atomic_revision_and_replay_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, manifest = _approved_pending_authorization()
    before = _json_bytes(manifest)

    class Store:
        def __init__(self, value: dict) -> None:
            self.value = deepcopy(value)

        def load(self, run_id: str) -> dict:
            assert run_id == self.value["identity"]["run_id"]
            return deepcopy(self.value)

        def save(self, value: dict, *, expected_revision: int) -> dict:
            assert int(value["revision"]) == expected_revision + 1
            self.value = deepcopy(value)
            return deepcopy(value)

    store = Store(record)
    service = ComprehensiveRunService(store, {})  # type: ignore[arg-type]
    monkeypatch.setattr(
        run_service_module,
        "attach_approved_delivery_package",
        attach_approved_delivery_package,
    )
    authorized = service.authorize_delivery(
        record["identity"]["run_id"],
        authorizer="Alice Security",
        authorizer_role="Cybersecurity specialist",
        authorization_reason="Explicit client delivery authorization.",
        authorized_at="2026-08-21T15:05:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )

    assert authorized["revision"] == record["revision"] + 1
    assert authorized["client_delivery_allowed"] is True
    assert _json_bytes(authorized["accepted_edition"]) == before
    assert validate_approved_delivery_package(
        authorized,
        authorized["approved_delivery_package"],
    )["status"] == "valid"
    with pytest.raises(ValueError, match="client_delivery_already_authorized"):
        service.authorize_delivery(
            record["identity"]["run_id"],
            authorizer="Alice Security",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Replay.",
            authorized_at="2026-08-21T15:06:00+00:00",
            expected_artifact_identity=review_artifact_identity(authorized),
        )


def test_delivery_authorization_rejects_stale_replay_and_invalid_human_authority() -> None:
    record, manifest = _approved_pending_authorization()
    identity = review_artifact_identity(record)
    stale = deepcopy(identity)
    stale["artifact_digests"]["pdf"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        authorize_accepted_edition(
            record,
            manifest,
            authorizer="Alice Security",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Explicit authorization.",
            authorized_at="2026-08-21T15:05:00+00:00",
            expected_artifact_identity=stale,
        )
    with pytest.raises(ValueError, match="automation_cannot_create_final_human_approval"):
        authorize_accepted_edition(
            record,
            manifest,
            authorizer="automation",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Automated authorization is forbidden.",
            authorized_at="2026-08-21T15:05:00+00:00",
            expected_artifact_identity=identity,
        )

    authorization = authorize_accepted_edition(
        record,
        manifest,
        authorizer="Alice Security",
        authorizer_role="Cybersecurity specialist",
        authorization_reason="Explicit authorization.",
        authorized_at="2026-08-21T15:05:00+00:00",
        expected_artifact_identity=identity,
    )
    record["delivery_authorization"] = authorization
    with pytest.raises(ValueError, match="client_delivery_already_authorized"):
        authorize_accepted_edition(
            record,
            manifest,
            authorizer="Alice Security",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Replay.",
            authorized_at="2026-08-21T15:06:00+00:00",
            expected_artifact_identity=identity,
        )


@pytest.mark.parametrize("status", ["review_required", "rejected", "failed"])
def test_delivery_authorization_rejects_nonapproved_runs(status: str) -> None:
    record, manifest = _approved_pending_authorization()
    record["status"] = status
    with pytest.raises(ValueError, match="delivery_authorization_requires_approved_run"):
        authorize_accepted_edition(
            record,
            manifest,
            authorizer="Alice Security",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Invalid state.",
            authorized_at="2026-08-21T15:05:00+00:00",
            expected_artifact_identity=review_artifact_identity(record),
        )


def test_delivery_authorization_rejects_tampered_manifest_and_pdf() -> None:
    record, manifest = _approved_pending_authorization()
    tampered_manifest = deepcopy(manifest)
    tampered_manifest["report_artifact_digest"] = "0" * 64
    with pytest.raises(ValueError, match="accepted_edition_manifest_hash_mismatch"):
        authorize_accepted_edition(
            record,
            tampered_manifest,
            authorizer="Alice Security",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Invalid manifest.",
            authorized_at="2026-08-21T15:05:00+00:00",
            expected_artifact_identity=review_artifact_identity(record),
        )

    authorization = authorize_accepted_edition(
        record,
        manifest,
        authorizer="Alice Security",
        authorizer_role="Cybersecurity specialist",
        authorization_reason="Explicit authorization.",
        authorized_at="2026-08-21T15:05:00+00:00",
        expected_artifact_identity=review_artifact_identity(record),
    )
    record["stage_results"]["final_comprehensive_report_generation"]["report_package"][
        "pdf_base64"
    ] = base64.b64encode(b"%PDF-1.7 tampered").decode("ascii")
    validation = validate_delivery_authorization(record, manifest, authorization)
    assert validation["status"] == "invalid"
    assert any(
        "accepted_edition" in error or "current_artifact_mismatch" in error
        for error in validation["validation_errors"]
    )


def test_cross_project_mutation_invalidates_delivery() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    tampered = deepcopy(attached)
    tampered["identity"]["project_id"] = "other-project"
    validation = validate_approved_delivery_package(
        tampered,
        tampered["approved_delivery_package"],
    )
    assert validation["status"] == "invalid"
    assert "phase4_project_id_mismatch" in validation["validation_errors"]
    assert "review_work_projection_invalid" in validation["validation_errors"]
    assert any(
        item.startswith("phase4_inherited_validation_failed:")
        for item in validation["validation_errors"]
    )


def test_report_regeneration_after_approval_invalidates_receipt() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    tampered = deepcopy(attached)
    package = tampered["stage_results"]["final_comprehensive_report_generation"]["report_package"]
    package["markdown"] += "\nRegenerated after approval.\n"
    validation = validate_approved_delivery_package(tampered, tampered["approved_delivery_package"])
    assert validation["status"] == "invalid"
    assert "exact_artifact_hash_binding_invalid" in validation["validation_errors"]
    assert "delivery_authorization_current_artifact_mismatch:artifact_digests" in validation[
        "validation_errors"
    ]


def test_accepted_reviewer_identity_cannot_be_rewritten_after_approval() -> None:
    decision_record, manifest = _decision_and_manifest()
    manifest = deepcopy(manifest)
    manifest["review"]["reviewer"] = "automation"
    with pytest.raises(ValueError, match="accepted_edition_manifest_hash_mismatch"):
        bind_phase4_approval_manifest(decision_record, manifest)


def test_internal_assessment_cannot_become_phase4_client_final() -> None:
    decision_record, manifest = _decision_and_manifest()
    decision_record = deepcopy(decision_record)
    evidence = decision_record["human_evidence"]["modules"]["stakeholder_context"]["evidence"]
    evidence["engagement_mode"] = ["internal"]
    with pytest.raises(ValueError, match="internal_or_test_assessment_not_client_final"):
        attach_approved_delivery_package(decision_record, manifest)


def test_receipt_derived_certificate_fields_cannot_be_rewritten_with_a_new_self_hash() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = deepcopy(attached["approved_delivery_package"])
    certificate = delivery["certificate"]
    certificate["reviewer_identity"] = "Mallory"
    certificate.pop("delivery_authorization_certificate_sha256", None)
    certificate["delivery_authorization_certificate_sha256"] = canonical_sha256(certificate)

    validation = validate_approved_delivery_package(attached, delivery)

    assert validation["status"] == "invalid"
    assert "phase4_reviewer_identity_mismatch" in validation["validation_errors"]


def test_in_memory_and_archived_delivery_manifests_must_be_identical() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = deepcopy(attached["approved_delivery_package"])
    delivery["manifest"]["artifacts"][0]["sha256"] = "0" * 64

    validation = validate_approved_delivery_package(attached, delivery)

    assert validation["status"] == "invalid"
    assert "phase4_evidence_manifest_archive_mismatch" in validation["validation_errors"]


def test_top_level_receipt_binding_cannot_diverge_from_exact_receipt() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = deepcopy(attached["approved_delivery_package"])
    delivery["phase4_approval_receipt_sha256"] = "0" * 64

    validation = validate_approved_delivery_package(attached, delivery)

    assert validation["status"] == "invalid"
    assert "phase4_receipt_package_hash_mismatch" in validation["validation_errors"]


def test_fully_rehashed_archive_cannot_replace_exact_approval_record_or_pdf() -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = attached["approved_delivery_package"]

    forged_approval = deepcopy(attached["accepted_edition"])
    forged_approval["review"]["reviewer"] = "Mallory Security"
    approval_delivery = _fully_rehash_archive(
        delivery,
        entry_changes={"15_approval_record.json": _json_bytes(forged_approval)},
    )
    approval_validation = validate_approved_delivery_package(
        attached,
        approval_delivery,
    )
    assert approval_validation["status"] == "invalid"
    assert (
        "phase4_approval_record_accepted_edition_mismatch"
        in approval_validation["validation_errors"]
    )

    with zipfile.ZipFile(
        io.BytesIO(base64.b64decode(delivery["zip_base64"], validate=True)),
        "r",
    ) as archive:
        original_pdf = archive.read("01_nico_comprehensive_report.pdf")
    pdf_delivery = _fully_rehash_archive(
        delivery,
        entry_changes={
            "01_nico_comprehensive_report.pdf": original_pdf + b"\n% forged\n"
        },
    )
    pdf_validation = validate_approved_delivery_package(attached, pdf_delivery)
    assert pdf_validation["status"] == "invalid"
    assert "phase4_authorized_edition_pdf_mismatch" in pdf_validation[
        "validation_errors"
    ]


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("repository", "OtherOrg/other", "phase4_evidence_manifest_repository_mismatch"),
        ("run_id", "comprun_other", "phase4_evidence_manifest_run_id_mismatch"),
        ("product_name", "Other product", "phase4_evidence_manifest_product_name_mismatch"),
        (
            "package_classification",
            "internal",
            "phase4_evidence_manifest_package_classification_mismatch",
        ),
        (
            "client_delivery_allowed",
            False,
            "phase4_evidence_manifest_delivery_authorization_missing",
        ),
        (
            "human_review_required",
            False,
            "phase4_evidence_manifest_human_review_boundary_missing",
        ),
        (
            "delivery_authorization_sha256",
            "0" * 64,
            "phase4_evidence_manifest_delivery_authorization_hash_mismatch",
        ),
    ],
)
def test_fully_rehashed_archive_manifest_cannot_change_identity_or_boundary(
    field: str,
    value: object,
    expected_error: str,
) -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    forged = _fully_rehash_archive(
        attached["approved_delivery_package"],
        manifest_changes={field: value},
    )
    validation = validate_approved_delivery_package(attached, forged)
    assert validation["status"] == "invalid"
    assert expected_error in validation["validation_errors"]


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        (
            "approval_certificate_sha256",
            "0" * 64,
            "phase4_approval_certificate_sha256_mismatch",
        ),
        ("approved_at", "2026-01-01T00:00:00+00:00", "phase4_approved_at_mismatch"),
        (
            "report_analysis_regenerated_during_delivery_packaging",
            True,
            "phase4_certificate_report_regeneration_invalid",
        ),
        (
            "approval_certificate_page_appended",
            True,
            "phase4_certificate_approved_pdf_was_mutated",
        ),
    ],
)
def test_rehashed_certificate_cannot_contradict_exact_approval(
    field: str,
    value: object,
    expected_error: str,
) -> None:
    decision_record, manifest = _decision_and_manifest()
    attached = attach_approved_delivery_package(decision_record, manifest)
    delivery = deepcopy(attached["approved_delivery_package"])
    certificate = delivery["certificate"]
    certificate[field] = value
    certificate.pop("delivery_authorization_certificate_sha256", None)
    certificate["delivery_authorization_certificate_sha256"] = canonical_sha256(
        certificate
    )
    validation = validate_approved_delivery_package(attached, delivery)
    assert validation["status"] == "invalid"
    assert expected_error in validation["validation_errors"]


def test_automated_delivery_is_authorized_without_claiming_human_review() -> None:
    record = deepcopy(_record_template())
    identity = review_artifact_identity(record)
    package = build_automated_delivery_package(
        record,
        expected_artifact_identity=identity,
        authorized_at="2026-09-03T22:00:00+00:00",
    )

    assert package["status"] == "authorized"
    assert package["client_facing_status"] == "authorized_automated_technical_assessment"
    assert package["authorization_mode"] == "automated_policy"
    assert package["human_reviewed"] is False
    assert package["human_review_required"] is False
    assert package["client_delivery_allowed"] is True

    payload = base64.b64decode(package["zip_base64"], validate=True)
    assert _sha256(payload) == package["zip_sha256"]
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        authorization = json.loads(archive.read("07_automated_authorization.json"))
        report_json = json.loads(archive.read("02_nico_comprehensive_report.json"))
        report_markdown = archive.read("03_nico_comprehensive_report.md").decode()
        report_pdf = archive.read("01_nico_comprehensive_report.pdf")

    assert authorization["human_reviewed"] is False
    assert authorization["security_certification"] is False
    assert report_json["client_facing_status"] == "authorized_automated_technical_assessment"
    assert report_json["human_review_completed"] is False
    assert "PENDING HUMAN APPROVAL" not in report_markdown
    assert "AUTHORIZED FINAL" in report_markdown

    from pypdf import PdfReader

    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(report_pdf)).pages
    )
    assert "AUTHORIZED AUTOMATED TECHNICAL ASSESSMENT" in pdf_text
    assert "Human reviewed" in pdf_text
    assert "NO" in pdf_text
    assert "No human cybersecurity specialist reviewed or certified this report." in pdf_text
