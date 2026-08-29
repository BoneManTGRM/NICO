from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import (
    ComprehensiveApiController,
    _final_report_package_integrity_bound,
)
from nico.comprehensive_review_decision_v1 import review_artifact_identity
from nico.comprehensive_pending_artifact_metadata_repair_v1 import (
    repair_pending_findings_csv_alias,
)
from nico.comprehensive_review_work_runtime_v1 import (
    install_comprehensive_review_work_runtime_v1,
)
from nico.comprehensive_run_record import _record_hash, validate_comprehensive_run_record
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.phase4_client_delivery_runtime_v1 import (
    install_phase4_client_delivery_runtime_v1,
)
from tests.test_phase4_authorized_artifact_routes_integration_v1 import (
    _app,
    _authorized_phase4_record,
)
from tests.test_v2_premium_report_renderer import _package


class _Store:
    def __init__(self, record: dict) -> None:
        self.record = deepcopy(record)

    def load(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return deepcopy(self.record)

    def save(self, record: dict, *, expected_revision: int) -> dict:
        assert record["revision"] == expected_revision + 1
        validation = validate_comprehensive_run_record(record)
        assert validation["status"] == "valid", validation
        self.record = deepcopy(record)
        return deepcopy(record)


@pytest.fixture(scope="module")
def authorized_record() -> dict:
    install_comprehensive_review_work_runtime_v1()
    install_phase4_client_delivery_runtime_v1(FastAPI())
    record = _authorized_phase4_record()
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    assert _final_report_package_integrity_bound(
        record["stage_results"]["final_comprehensive_report_generation"][
            "report_package"
        ]
    )
    return record


@pytest.fixture(scope="module")
def manifest_report(authorized_record: dict) -> dict:
    source = _package("en")
    identity = authorized_record["identity"]
    source["json"]["identity"].update(
        {
            "run_id": identity["run_id"],
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
            "evidence_ledger_id": identity["evidence_ledger_id"],
            "assessment_depth": identity["assessment_depth"],
        }
    )
    report = rebuild_client_artifacts(source)
    assert _final_report_package_integrity_bound(report)
    return report


def _review_ready(record: dict) -> dict:
    output = deepcopy(record)
    for field in (
        "accepted_edition",
        "approved_delivery_package",
        "delivery_authorization",
        "review_context",
        "review_decision",
        "review_history",
    ):
        output.pop(field, None)
    output.update(
        {
            "status": "review_required",
            "terminal": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
        }
    )
    output["integrity_sha256"] = _record_hash(output)
    assert validate_comprehensive_run_record(output)["status"] == "valid"
    return output


def _approved_pending_delivery(record: dict) -> dict:
    output = deepcopy(record)
    for field in ("approved_delivery_package", "delivery_authorization"):
        output.pop(field, None)
    output["client_delivery_allowed"] = False
    output["integrity_sha256"] = _record_hash(output)
    assert validate_comprehensive_run_record(output)["status"] == "valid"
    return output


def _corrupt_canonical_truth_hash(record: dict) -> dict:
    output = deepcopy(record)
    report = output["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]
    report["canonical_truth_sha256"] = "0" * 64
    output["integrity_sha256"] = _record_hash(output)
    assert validate_comprehensive_run_record(output)["status"] == "valid"
    return output


def _apply_legacy_findings_csv_alias_defect(record: dict) -> dict:
    output = deepcopy(record)
    stage_results = output["stage_results"]
    final_stage = stage_results["final_comprehensive_report_generation"]
    evidence = dict(final_stage.get("evidence") or {})
    evidence.update(
        {
            "v2_single_source_pipeline": True,
            "final_artifact_generation_complete": True,
        }
    )
    final_stage["evidence"] = evidence
    stage_results.setdefault(
        "cross_format_truth_verification",
        {
            "status": "complete",
            "failed_checks": [],
            "final_artifact_truth": {"status": "verified", "failed_checks": []},
        },
    )
    stage_results.setdefault("human_review_request", {"status": "complete"})
    stage_results.setdefault(
        "client_acceptance_pending", {"status": "review_required"}
    )
    report = final_stage["report_package"]
    legacy_bytes = b"legacy,v2,findings,csv\n"
    assert legacy_bytes != report["findings_csv"].encode("utf-8")
    report["findings_csv_base64"] = base64.b64encode(legacy_bytes).decode("ascii")
    report["findings_csv_sha256"] = hashlib.sha256(legacy_bytes).hexdigest()
    output["integrity_sha256"] = _record_hash(output)
    assert validate_comprehensive_run_record(output)["status"] == "valid"
    assert _final_report_package_integrity_bound(report) is False
    return output


def _rehash_canonical_and_detached_manifest(report: dict) -> None:
    canonical_json = json.dumps(
        report["json"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    canonical_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    report["canonical_json"] = canonical_json
    report["canonical_json_sha256"] = canonical_sha256
    report["canonical_truth_sha256"] = canonical_sha256
    if "json_sha256" in report:
        report["json_sha256"] = canonical_sha256

    detached_canonical = next(
        item
        for item in report["artifact_manifest"]["artifacts"]
        if item["artifact_type"] == "canonical_json"
    )
    detached_canonical["sha256"] = canonical_sha256
    detached_canonical["size_bytes"] = len(canonical_json.encode("utf-8"))
    evidence_manifest_json = json.dumps(
        report["artifact_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    evidence_manifest_sha256 = hashlib.sha256(
        evidence_manifest_json.encode("utf-8")
    ).hexdigest()
    report["evidence_manifest_json"] = evidence_manifest_json
    report["evidence_manifest_sha256"] = evidence_manifest_sha256
    report["draft_artifact_identity"][
        "canonical_json_sha256"
    ] = canonical_sha256
    report["draft_artifact_identity"][
        "evidence_manifest_sha256"
    ] = evidence_manifest_sha256


def test_invalid_final_package_blocks_every_human_authority_transition(
    authorized_record: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_ready = _corrupt_canonical_truth_hash(_review_ready(authorized_record))
    projected = ComprehensiveApiController._response(
        review_ready,
        operation="status",
    )
    assert projected["status"] == "blocked"
    assert projected["approval_status"] == "invalidated_artifact_mismatch"
    assert projected["response_projection"]["artifact_integrity_valid"] is False

    review_service = ComprehensiveRunService(_Store(review_ready), {})
    with pytest.raises(
        ValueError,
        match="comprehensive_report_artifact_integrity_invalid",
    ):
        review_service.review(
            review_ready["identity"]["run_id"],
            reviewer="Authorized Security Reviewer",
            reviewer_role="Cybersecurity specialist",
            decision="approved",
            decision_reason="Reviewed exact immutable artifacts.",
            decided_at="2026-08-28T12:00:00+00:00",
            expected_artifact_identity=review_artifact_identity(review_ready),
        )

    with pytest.raises(
        ValueError,
        match="comprehensive_report_artifact_integrity_invalid",
    ):
        review_service.review_work(
            review_ready["identity"]["run_id"],
            {
                "action": "disposition_candidate",
                "candidate_id": "candidate-phase4-1",
                "disposition": "false_positive",
                "rationale": "Exact retained evidence supports this disposition.",
                "reviewer": "Authorized Security Reviewer",
                "reviewer_role": "Cybersecurity specialist",
                "review_authorized": True,
                "authorization_confirmed": True,
            },
        )

    monkeypatch.setattr(routes, "_authorize_review", lambda _token: None)
    review_work_read = TestClient(_app(review_ready)).get(
        "/assessment/comprehensive-run/"
        f"{review_ready['identity']['run_id']}/review-work",
        headers={"X-NICO-Admin-Token": "test-only-authorized-token"},
    )
    assert review_work_read.status_code == 422
    assert review_work_read.json()["detail"] == (
        "comprehensive_report_artifact_integrity_invalid"
    )

    approved = _corrupt_canonical_truth_hash(
        _approved_pending_delivery(authorized_record)
    )
    delivery_service = ComprehensiveRunService(_Store(approved), {})
    with pytest.raises(
        ValueError,
        match="comprehensive_report_artifact_integrity_invalid",
    ):
        delivery_service.authorize_delivery(
            approved["identity"]["run_id"],
            authorizer="Authorized Security Reviewer",
            authorizer_role="Cybersecurity specialist",
            authorization_reason="Authorize this exact accepted edition.",
            authorized_at="2026-08-28T12:05:00+00:00",
            expected_artifact_identity=review_artifact_identity(approved),
        )

    authorized = _corrupt_canonical_truth_hash(authorized_record)
    with pytest.raises(HTTPException) as blocked_download:
        routes._approved_delivery_response(authorized)
    assert blocked_download.value.status_code == 409
    assert blocked_download.value.detail["code"] == (
        "approved_delivery_package_integrity_invalid"
    )
    assert blocked_download.value.detail["client_delivery_allowed"] is False


def test_pdf_substitution_cannot_hide_behind_a_stripped_manifest_entry(
    authorized_record: dict,
    manifest_report: dict,
) -> None:
    record = _review_ready(authorized_record)
    final_stage = record["stage_results"]["final_comprehensive_report_generation"]
    final_stage["report_package"] = deepcopy(manifest_report)
    final_stage["assessment"] = deepcopy(manifest_report["json"]["assessment"])
    report = final_stage["report_package"]
    substituted_pdf = b"%PDF-1.4\nsubstituted report bytes\n%%EOF\n"
    substituted_sha256 = hashlib.sha256(substituted_pdf).hexdigest()
    report["pdf_base64"] = base64.b64encode(substituted_pdf).decode("ascii")
    report["pdf_sha256"] = substituted_sha256
    report["draft_artifact_identity"]["pdf_sha256"] = substituted_sha256

    detached = deepcopy(report["artifact_manifest"])
    detached["artifacts"] = [
        item
        for item in detached["artifacts"]
        if item.get("artifact_type") != "comprehensive_pdf"
    ]
    detached_json = json.dumps(
        detached,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    detached_sha256 = hashlib.sha256(detached_json.encode("utf-8")).hexdigest()
    report["artifact_manifest"] = detached
    report["evidence_manifest_json"] = detached_json
    report["evidence_manifest_sha256"] = detached_sha256
    report["draft_artifact_identity"][
        "evidence_manifest_sha256"
    ] = detached_sha256
    record["integrity_sha256"] = _record_hash(record)

    assert _final_report_package_integrity_bound(report) is False
    client = TestClient(_app(record))
    run_id = record["identity"]["run_id"]
    for path in ("report/pdf", "localized-report/en/pdf"):
        response = client.get(f"/assessment/comprehensive-run/{run_id}/{path}")
        assert response.status_code == 409


def test_resume_repairs_only_the_known_pending_v2_findings_csv_alias(
    authorized_record: dict,
) -> None:
    affected = _apply_legacy_findings_csv_alias_defect(
        _review_ready(authorized_record)
    )
    previous_revision = int(affected["revision"])
    previous_report = affected["stage_results"][
        "final_comprehensive_report_generation"
    ]["report_package"]
    previous_manifest = deepcopy(previous_report["artifact_manifest"])
    previous_pdf = previous_report["pdf_base64"]

    service = ComprehensiveRunService(_Store(affected), {})
    repaired = service.resume(affected["identity"]["run_id"])
    report = repaired["stage_results"]["final_comprehensive_report_generation"][
        "report_package"
    ]

    assert repaired["revision"] == previous_revision + 1
    assert repaired["status"] == "review_required"
    assert repaired["terminal"] is True
    assert repaired["human_review_completed"] is False
    assert repaired["client_delivery_allowed"] is False
    assert report["artifact_manifest"] == previous_manifest
    assert report["pdf_base64"] == previous_pdf
    assert base64.b64decode(report["findings_csv_base64"], validate=True) == (
        report["findings_csv"].encode("utf-8")
    )
    assert report["findings_csv_sha256"] == hashlib.sha256(
        report["findings_csv"].encode("utf-8")
    ).hexdigest()
    assert _final_report_package_integrity_bound(report) is True
    assert repaired["artifact_metadata_repair_history"][-1][
        "retained_artifact_bytes_changed"
    ] is False

    # The migration is durable and idempotent; a second continuation is a no-op.
    assert service.resume(affected["identity"]["run_id"]) == repaired


def test_pending_alias_repair_keeps_unknown_integrity_failures_blocked(
    authorized_record: dict,
) -> None:
    affected = _apply_legacy_findings_csv_alias_defect(
        _corrupt_canonical_truth_hash(_review_ready(authorized_record))
    )

    assert repair_pending_findings_csv_alias(affected) == affected


def test_pending_alias_repair_never_mutates_reviewed_artifacts(
    authorized_record: dict,
) -> None:
    affected = _apply_legacy_findings_csv_alias_defect(authorized_record)

    assert repair_pending_findings_csv_alias(affected) == affected


@pytest.mark.parametrize(
    "digest_field",
    (
        "findings_csv_sha256",
        "evidence_csv_sha256",
        "candidate_register_sha256",
        "remediation_backlog_sha256",
    ),
)
def test_public_auxiliary_digest_claims_must_match_retained_bytes(
    manifest_report: dict,
    digest_field: str,
) -> None:
    report = deepcopy(manifest_report)
    report[digest_field] = "0" * 64

    assert _final_report_package_integrity_bound(report) is False


@pytest.mark.parametrize(
    "artifact_type",
    ("canonical_json", "evidence_manifest_json"),
)
def test_canonical_manifest_self_reference_rows_must_keep_run_lineage(
    manifest_report: dict,
    artifact_type: str,
) -> None:
    report = deepcopy(manifest_report)
    row = next(
        item
        for item in report["json"]["artifact_manifest"]["artifacts"]
        if item["artifact_type"] == artifact_type
    )
    row["run_id"] = "comprun-substituted"
    row["commit_sha"] = "0" * 40

    _rehash_canonical_and_detached_manifest(report)

    assert _final_report_package_integrity_bound(report) is False


@pytest.mark.parametrize(
    ("field", "substituted"),
    (
        ("customer_id", "customer-substituted"),
        ("project_id", "project-substituted"),
        ("report_language", "es-MX"),
        ("generation_timestamp", "2099-01-01T00:00:00Z"),
    ),
)
def test_detached_and_canonical_manifest_identity_cannot_split_from_truth(
    manifest_report: dict,
    field: str,
    substituted: str,
) -> None:
    report = deepcopy(manifest_report)
    report["artifact_manifest"]["identity"][field] = substituted
    report["json"]["artifact_manifest"]["identity"][field] = substituted

    _rehash_canonical_and_detached_manifest(report)

    assert _final_report_package_integrity_bound(report) is False


def test_detached_manifest_cannot_fabricate_human_approval_or_delivery(
    manifest_report: dict,
) -> None:
    report = deepcopy(manifest_report)
    report["artifact_manifest"]["lifecycle"].update(
        {
            "report_finality": "approved_final",
            "human_review_status": "approved",
            "client_delivery_status": "authorized",
            "client_delivery_allowed": True,
        }
    )
    report["artifact_manifest"]["approval"].update(
        {
            "reviewer_identity": "Fabricated Bot",
            "reviewer_role": "system",
            "reviewer_authorized": True,
            "decision": "approved",
            "client_delivery_allowed": True,
        }
    )
    evidence_manifest_json = json.dumps(
        report["artifact_manifest"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    evidence_manifest_sha256 = hashlib.sha256(
        evidence_manifest_json.encode("utf-8")
    ).hexdigest()
    report["evidence_manifest_json"] = evidence_manifest_json
    report["evidence_manifest_sha256"] = evidence_manifest_sha256
    report["draft_artifact_identity"][
        "evidence_manifest_sha256"
    ] = evidence_manifest_sha256

    assert _final_report_package_integrity_bound(report) is False


def test_canonical_json_cannot_fabricate_human_approval_or_delivery(
    manifest_report: dict,
) -> None:
    report = deepcopy(manifest_report)
    report["json"]["lifecycle"].update(
        {
            "report_finality": "approved_final",
            "human_review_status": "approved",
            "client_delivery_status": "authorized",
            "client_delivery_allowed": True,
        }
    )
    report["json"]["approval"].update(
        {
            "reviewer_identity": "Fabricated Bot",
            "reviewer_role": "system",
            "reviewer_authorized": True,
            "decision": "approved",
            "client_delivery_allowed": True,
        }
    )

    _rehash_canonical_and_detached_manifest(report)

    assert _final_report_package_integrity_bound(report) is False


@pytest.mark.parametrize("container_name", ("json", "assessment"))
def test_canonical_duplicate_authority_fields_cannot_claim_approval(
    manifest_report: dict,
    container_name: str,
) -> None:
    report = deepcopy(manifest_report)
    container = (
        report["json"]
        if container_name == "json"
        else report["json"]["assessment"]
    )
    container.update(
        {
            "human_review_completed": True,
            "client_delivery_allowed": True,
            "report_finality": "approved_final",
            "approval_status": "approved_final",
            "delivery_status": "authorized",
            "human_review_status": "approved",
            "client_delivery_status": "authorized",
        }
    )

    _rehash_canonical_and_detached_manifest(report)

    assert _final_report_package_integrity_bound(report) is False


def test_strict_queue_and_review_work_reject_legacy_stage_candidate_fallback(
    authorized_record: dict,
    manifest_report: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _review_ready(authorized_record)
    final_stage = record["stage_results"][
        "final_comprehensive_report_generation"
    ]
    legacy_package = deepcopy(final_stage["report_package"])
    legacy_register = legacy_package["json"]["assessment"].get(
        "canonical_scanner_finding_register"
    )
    assert isinstance(legacy_register, dict)
    assert int(legacy_register["candidate_record_count"]) > 0

    final_stage["report_package"] = deepcopy(manifest_report)
    final_stage["assessment"] = deepcopy(
        manifest_report["json"]["assessment"]
    )
    assert not isinstance(
        manifest_report["json"]["assessment"].get(
            "canonical_scanner_finding_register"
        ),
        dict,
    )
    record["stage_results"]["reports"] = {
        "status": "complete",
        "report_package": legacy_package,
    }
    record["integrity_sha256"] = _record_hash(record)
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    assert _final_report_package_integrity_bound(
        final_stage["report_package"]
    )

    service = ComprehensiveRunService(_Store(record), {})
    with pytest.raises(
        ValueError,
        match="review_work_canonical_register_unavailable",
    ):
        service.review_work(
            record["identity"]["run_id"],
            {
                "action": "disposition_candidate",
                "candidate_id": "candidate-phase4-1",
                "disposition": "false_positive",
                "rationale": (
                    "A legacy-stage candidate must not become review authority."
                ),
                "reviewer": "Authorized Security Reviewer",
                "reviewer_role": "Cybersecurity specialist",
                "review_authorized": True,
                "authorization_confirmed": True,
            },
        )

    monkeypatch.setattr(routes, "_authorize_review", lambda _token: None)
    client = TestClient(_app(record))
    prefix = (
        "/assessment/comprehensive-run/"
        f"{record['identity']['run_id']}"
    )
    strict = client.get(
        f"{prefix}/review-queue",
        headers={"X-NICO-Admin-Token": "test-only-authorized-token"},
    )
    review_work = client.get(
        f"{prefix}/review-work",
        headers={"X-NICO-Admin-Token": "test-only-authorized-token"},
    )

    assert strict.status_code == 409
    assert strict.json()["detail"]["code"] == (
        "comprehensive_review_queue_register_unavailable"
    )
    assert review_work.status_code == 422
    assert review_work.json()["detail"] == (
        "review_work_canonical_register_unavailable"
    )


@pytest.mark.parametrize("decision", ("rejected", "request_more_evidence"))
def test_production_review_wrapper_rejects_stale_identity_for_every_decision(
    authorized_record: dict,
    decision: str,
) -> None:
    review_ready = _review_ready(authorized_record)
    stale_identity = review_artifact_identity(review_ready)
    stale_identity["revision"] = int(stale_identity["revision"]) - 1
    service = ComprehensiveRunService(_Store(review_ready), {})

    with pytest.raises(ValueError, match="stale_review_artifact_identity"):
        service.review(
            review_ready["identity"]["run_id"],
            reviewer="Authorized Security Reviewer",
            reviewer_role="Cybersecurity specialist",
            decision=decision,
            decision_reason="Decision applies only to the exact visible artifacts.",
            decided_at="2026-08-28T12:10:00+00:00",
            expected_artifact_identity=stale_identity,
        )
