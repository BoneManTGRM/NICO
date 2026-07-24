from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico.mid_assessment_report import (
    DRAFT_LABEL,
    MID_REPORT_PATH,
    MID_REPORT_TYPE,
    MID_REPORT_VERSION,
    generate_mid_draft_report,
)
from nico.mid_report_api import (
    MidDraftReportRequest,
    mid_draft_report_pdf_response,
    mid_draft_report_response,
)
from nico.storage import STORE


def _run_id() -> str:
    return f"midrun_report_{uuid4().hex[:12]}"


def _section(section_id: str, status: str, *, score=88, evidence=None, missing=None, failed=None, source="repository_evidence") -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green" if status == "Verified" else "yellow",
        "truth_status": status,
        "summary": f"Evidence-bound summary for {section_id}.",
        "evidence": evidence or [f"Direct evidence for {section_id}."],
        "findings": [],
        "unavailable": [],
        "missing_evidence_sources": missing or [],
        "failed_evidence_tools": failed or [],
        "source_classification": source,
        "direct_repository_proof": source == "repository_evidence",
        "human_review_required": status != "Verified",
        "unsupported_claims_permitted": False,
    }


def _truth() -> dict:
    sections = [
        _section("code_audit", "Verified"),
        _section("dependency_health", "Verified with limitations", missing=["dependency_scanners"]),
        _section("secrets_review", "Verified"),
        _section("static_analysis", "Failed", failed=["semgrep"], missing=["static_scanners"]),
        _section("ci_cd", "Verified with limitations", missing=["ci_runtime"]),
        _section("architecture_debt", "Verified"),
        _section("velocity_complexity", "Verified with limitations", missing=["activity_history"]),
        _section("functional_qa", "Human review required", score=None, evidence=["User submitted field: application_url"], source="user_submitted_external_context"),
        _section("platform_parity", "Unavailable", score=None, evidence=[], missing=["ios_build_access", "android_build_access"], source="unavailable"),
        _section("architecture_context", "Unavailable", score=None, evidence=[], missing=["architecture_documents"], source="unavailable"),
        _section("stakeholder_alignment", "Unavailable", score=None, evidence=[], missing=["meeting_transcripts"], source="unavailable"),
        _section("business_roadmap", "Unavailable", score=None, evidence=[], missing=["business_priorities"], source="unavailable"),
    ]
    return {
        "version": "mid-truth-status-v1",
        "allowed_statuses": ["Verified", "Verified with limitations", "Unavailable", "Failed", "Human review required"],
        "sections": sections,
        "summary": {
            "section_count": len(sections),
            "verified": 3,
            "verified_with_limitations": 3,
            "unavailable": 4,
            "failed": 1,
            "human_review_required": 1,
            "items_requiring_review": 9,
            "unavailable_evidence_sources": 9,
            "unsupported_claims_permitted": 0,
        },
        "evidence_coverage": {
            "label": "Automated evidence coverage",
            "calculated": True,
            "percent": 75,
            "numerator": 9,
            "denominator": 12,
            "method": "Percentage of twelve explicit evidence units available for this exact Mid run. Maturity scores do not affect coverage.",
            "units": [
                {"id": "repository_snapshot", "label": "Exact repository snapshot", "available": True, "status": "Verified", "evidence": "snapshot attached", "limitation": ""},
                {"id": "static_scanners", "label": "Static-analysis scanners", "available": False, "status": "Unavailable", "evidence": "", "limitation": "Semgrep failed."},
                {"id": "activity_history", "label": "Activity history", "available": False, "status": "Unavailable", "evidence": "", "limitation": "Activity evidence unavailable."},
            ],
        },
        "unsupported_claims_permitted": 0,
        "rule": "Missing evidence cannot be represented as a clean result.",
    }


def _record(run_id: str, *, status: str = "complete", unsupported: int = 0) -> dict:
    truth = _truth()
    truth["summary"]["unsupported_claims_permitted"] = unsupported
    truth["unsupported_claims_permitted"] = unsupported
    return {
        "run_id": run_id,
        "customer_id": "customer_report",
        "project_id": "project_report",
        "workflow": "mid_assessment",
        "service_tier": "mid",
        "status": status,
        "repository": "BoneManTGRM/NICO",
        "snapshot_id": f"snapshot_{run_id}",
        "snapshot_commit_sha": "a" * 40,
        "request": {
            "mode": "mid",
            "client_name": "Example Client",
            "project_name": "Example Project",
            "build_reports": False,
            "create_final_review_request": False,
        },
        "response": {
            "status": status,
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "mid_truth_status": truth,
            "evidence_coverage": truth["evidence_coverage"],
            "assessment": {"sections": truth["sections"], "evidence_ledger": {"status": "available", "entry_count": 12}},
            "scanner_evidence": {"status": "attached", "failed_tools": ["semgrep"]},
            "optional_evidence": {"status": "submitted"},
            "export_truth_gate": {"status": "review_required", "blockers": ["Static scanner evidence failed."]},
        },
        "report_id": "",
        "approval_id": "",
    }


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")


def _put(run_id: str, **kwargs) -> dict:
    record = _record(run_id, **kwargs)
    STORE.put("assessment_runs", run_id, record)
    return record


def test_mid_report_requires_admin_authentication_and_exact_scope():
    run_id = _run_id()
    _put(run_id)

    unauthorized = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="wrong")
    wrong_customer = generate_mid_draft_report(run_id, "wrong", "project_report", admin_token="test-admin-token")
    wrong_project = generate_mid_draft_report(run_id, "customer_report", "wrong", admin_token="test-admin-token")

    assert unauthorized["status"] == "blocked"
    assert unauthorized["admin_write"]["configured"] is True
    assert wrong_customer["status"] == "not_found"
    assert wrong_project["status"] == "not_found"
    assert "snapshot" not in repr(wrong_customer).lower()


def test_mid_report_requires_completed_run_and_zero_unsupported_claims():
    running_id = _run_id()
    unsupported_id = _run_id()
    _put(running_id, status="running")
    _put(unsupported_id, unsupported=1)

    running = generate_mid_draft_report(running_id, "customer_report", "project_report", admin_token="test-admin-token")
    unsupported = generate_mid_draft_report(unsupported_id, "customer_report", "project_report", admin_token="test-admin-token")

    assert running["status"] == "blocked"
    assert "must complete" in running["error"]
    assert unsupported["status"] == "blocked"
    assert "permits unsupported claims" in unsupported["error"]


def test_report_has_strict_mid_identity_and_never_relabels_full_or_express_output():
    run_id = _run_id()
    _put(run_id)

    report = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    payload = report["formats"]["json"]

    assert report["status"] == "complete"
    assert report["record_type"] == "mid_assessment_report"
    assert report["report_version"] == MID_REPORT_VERSION
    assert report["report_type"] == MID_REPORT_TYPE
    assert report["report_path"] == MID_REPORT_PATH
    assert report["report_id"].startswith("mid_report_")
    assert report["run_id"] == run_id
    assert payload["title"] == "NICO MID ASSESSMENT"
    assert payload["draft_label"] == DRAFT_LABEL
    assert payload["report_type"] == "mid_assessment"
    assert payload["report_path"] == "mid_run"
    assert "Express" not in payload["title"]
    assert "Full Assessment" not in payload["title"]


def test_report_is_bound_to_run_snapshot_truth_and_review_packet_hashes():
    run_id = _run_id()
    record = _put(run_id)

    report = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    identity = report["source_identity"]
    payload = report["formats"]["json"]

    assert report["snapshot_id"] == record["snapshot_id"]
    assert report["snapshot_commit_sha"] == record["snapshot_commit_sha"]
    assert identity["run_id"] == run_id
    assert identity["snapshot_id"] == record["snapshot_id"]
    assert identity["snapshot_commit_sha"] == record["snapshot_commit_sha"]
    assert identity["review_packet_id"] == report["review_packet_id"]
    assert identity["review_packet_sha256"] == report["review_packet_sha256"]
    assert len(identity["truth_sha256"]) == 64
    assert len(report["source_identity_sha256"]) == 64
    assert payload["source_identity_sha256"] == report["source_identity_sha256"]
    assert payload["review_packet"]["review_packet_sha256"] == report["review_packet_sha256"]


def test_markdown_html_and_pdf_contain_draft_truth_and_integrity_material():
    run_id = _run_id()
    _put(run_id)

    report = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    markdown = report["formats"]["markdown"]
    html_report = report["formats"]["html"]
    pdf = base64.b64decode(report["formats"]["pdf"], validate=True)

    assert "# NICO MID ASSESSMENT" in markdown
    assert DRAFT_LABEL in markdown
    assert "Truth status: **Failed**" in markdown
    assert "Review by exception" in markdown
    assert "Unsupported claims permitted: 0" in markdown
    assert report["review_packet_sha256"] in markdown
    assert "NICO MID ASSESSMENT" in html_report
    assert DRAFT_LABEL in html_report
    assert "Automated evidence coverage" in html_report
    assert pdf.startswith(b"%PDF")
    assert hashlib.sha256(pdf).hexdigest() == report["pdf_sha256"]
    assert report["pdf_filename"].endswith("-FINAL-PENDING-APPROVAL.pdf")


def test_every_truth_section_is_preserved_in_report_payload():
    run_id = _run_id()
    record = _put(run_id)

    report = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    source_sections = record["response"]["mid_truth_status"]["sections"]
    report_sections = report["formats"]["json"]["sections"]

    assert len(report_sections) == len(source_sections) == 12
    assert [item["id"] for item in report_sections] == [item["id"] for item in source_sections]
    assert [item["truth_status"] for item in report_sections] == [item["truth_status"] for item in source_sections]
    assert all(item["unsupported_claims_permitted"] is False for item in report_sections)
    assert next(item for item in report_sections if item["id"] == "static_analysis")["failed_evidence_tools"] == ["semgrep"]
    assert next(item for item in report_sections if item["id"] == "functional_qa")["direct_repository_proof"] is False


def test_report_remains_draft_and_cannot_enable_approval_or_client_delivery():
    run_id = _run_id()
    _put(run_id)

    report = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    payload = report["formats"]["json"]

    assert report["draft_status"] == "human_review_required"
    assert report["human_review_required"] is True
    assert report["approval_required"] is True
    assert report["client_delivery_allowed"] is False
    assert report["approved"] is False
    assert report["unsupported_claims_permitted"] == 0
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed"] is False
    assert payload["approved"] is False


def test_unchanged_source_reuses_same_report_and_pdf_deterministically():
    run_id = _run_id()
    _put(run_id)

    first = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    second = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")

    assert first["report_id"] == second["report_id"]
    assert first["source_identity_sha256"] == second["source_identity_sha256"]
    assert first["pdf_sha256"] == second["pdf_sha256"]
    assert first["formats"]["pdf"] == second["formats"]["pdf"]
    assert second["idempotent_reuse"] is True


def test_truth_change_invalidates_report_identity_and_generates_new_draft():
    run_id = _run_id()
    _put(run_id)
    first = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    record = STORE.get("assessment_runs", run_id)
    record["response"]["mid_truth_status"]["sections"][0]["summary"] = "Changed verified evidence summary."
    STORE.put("assessment_runs", run_id, record)

    second = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")

    assert first["report_id"] != second["report_id"]
    assert first["source_identity_sha256"] != second["source_identity_sha256"]
    assert first["review_packet_sha256"] != second["review_packet_sha256"]


def test_run_state_stores_report_metadata_without_duplicate_pdf_bytes():
    run_id = _run_id()
    _put(run_id)

    report = generate_mid_draft_report(run_id, "customer_report", "project_report", admin_token="test-admin-token")
    stored = STORE.get("assessment_runs", run_id)
    metadata = stored["response"]["mid_report"]

    assert stored["report_id"] == report["report_id"]
    assert metadata["report_id"] == report["report_id"]
    assert metadata["report_path"] == "mid_run"
    assert metadata["pdf_sha256"] == report["pdf_sha256"]
    assert metadata["client_delivery_allowed"] is False
    assert "pdf" not in metadata
    assert "pdf_base64" not in repr(metadata)


def test_api_metadata_response_excludes_report_body_and_pdf():
    run_id = _run_id()
    _put(run_id)

    response = mid_draft_report_response(
        run_id,
        MidDraftReportRequest(customer_id="customer_report", project_id="project_report"),
        x_nico_admin_token="test-admin-token",
    )

    assert response["status"] == "complete"
    assert response["report_path"] == "mid_run"
    assert response["formats_available"] == {"json": True, "markdown": True, "html": True, "pdf": True}
    assert "formats" not in response
    assert "pdf_base64" not in repr(response)
    assert response["client_delivery_allowed"] is False
    assert response["approved"] is False


def test_pdf_api_returns_exact_hash_bound_no_store_pdf():
    run_id = _run_id()
    _put(run_id)
    metadata = mid_draft_report_response(
        run_id,
        MidDraftReportRequest(customer_id="customer_report", project_id="project_report"),
        x_nico_admin_token="test-admin-token",
    )

    response = mid_draft_report_pdf_response(
        run_id,
        customer_id="customer_report",
        project_id="project_report",
        x_nico_admin_token="test-admin-token",
    )

    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert hashlib.sha256(response.body).hexdigest() == metadata["pdf_sha256"]
    assert response.headers["x-nico-report-id"] == metadata["report_id"]
    assert response.headers["x-nico-pdf-sha256"] == metadata["pdf_sha256"]
    assert response.headers["x-nico-review-packet-sha256"] == metadata["review_packet_sha256"]
    assert response.headers["x-nico-source-identity-sha256"] == metadata["source_identity_sha256"]
    assert response.headers["x-nico-report-path"] == "mid_run"
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert "x-nico-pdf-sha256" in response.headers["access-control-expose-headers"].lower()


def test_api_uses_generic_auth_scope_and_incomplete_run_errors():
    run_id = _run_id()
    _put(run_id)

    with pytest.raises(HTTPException) as unauthorized:
        mid_draft_report_response(
            run_id,
            MidDraftReportRequest(customer_id="customer_report", project_id="project_report"),
            x_nico_admin_token="wrong",
        )
    with pytest.raises(HTTPException) as missing:
        mid_draft_report_response(
            run_id,
            MidDraftReportRequest(customer_id="wrong", project_id="project_report"),
            x_nico_admin_token="test-admin-token",
        )
    running_id = _run_id()
    _put(running_id, status="running")
    with pytest.raises(HTTPException) as running:
        mid_draft_report_response(
            running_id,
            MidDraftReportRequest(customer_id="customer_report", project_id="project_report"),
            x_nico_admin_token="test-admin-token",
        )

    assert unauthorized.value.status_code == 403
    assert missing.value.status_code == 404
    assert missing.value.detail["message"] == "Mid Assessment run not found."
    assert running.value.status_code == 409
