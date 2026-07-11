from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico import mid_optional_evidence as evidence
from nico.mid_assessment_runs import persist_mid_assessment_run
from nico.mid_optional_evidence_api import MidOptionalEvidenceRequest, mid_optional_evidence_response
from nico.storage import STORE


def _run_id() -> str:
    return f"midrun_optional_{uuid4().hex[:12]}"


def _persist_run(run_id: str) -> dict:
    result = {
        "status": "running",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_optional",
        "project_id": "project_optional",
        "repository_snapshot": {
            "status": "attached",
            "snapshot_id": f"snapshot_{run_id}",
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "scanner": {"scan_id": f"scan_{run_id}", "status": "queued"},
        "scanner_evidence": {"scan_id": f"scan_{run_id}", "status": "not_attached"},
        "reports": {"pdf_base64": ""},
    }
    persist_mid_assessment_run(
        result,
        {
            "run_id": run_id,
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_optional",
            "project_id": "project_optional",
            "authorized": True,
            "authorization_confirmed": True,
            "mode": "mid",
            "build_reports": False,
            "create_final_review_request": False,
        },
    )
    return result


def _access_record(run_id: str) -> dict:
    access_id = evidence._record_id(evidence.ACCESS_PREFIX, run_id)
    record = STORE.get("evidence_items", access_id)
    assert record is not None
    return record


def test_fresh_mid_run_returns_capability_once_without_retaining_raw_token():
    run_id = _run_id()
    result = _persist_run(run_id)
    submission = result["optional_evidence_submission"]
    token = submission["token"]

    assert submission["status"] == "issued"
    assert token.startswith("midevidence.")
    assert len(token) > 60
    access = _access_record(run_id)
    assert access["run_id"] == run_id
    assert access["snapshot_id"] == f"snapshot_{run_id}"
    assert access["snapshot_commit_sha"] == "a" * 40
    assert access["raw_token_stored"] is False
    assert token not in repr(access)
    assert token not in repr(STORE.get("assessment_runs", run_id))
    assert result["optional_evidence"]["status"] == "not_submitted"

    second = evidence.issue_mid_evidence_submission_access(run_id)
    assert second["status"] == "already_issued"
    assert "token" not in second


def test_submission_is_bound_to_run_snapshot_and_token_hash():
    first_id = _run_id()
    second_id = _run_id()
    first = _persist_run(first_id)
    second = _persist_run(second_id)

    wrong = evidence.submit_mid_optional_evidence(
        second_id,
        {"token": first["optional_evidence_submission"]["token"], "application_url": "https://staging.example.com"},
    )
    correct = evidence.submit_mid_optional_evidence(
        first_id,
        {"token": first["optional_evidence_submission"]["token"], "application_url": "https://staging.example.com"},
    )

    assert wrong["status"] == "not_found"
    assert correct["status"] == "submitted"
    summary = correct["optional_evidence"]
    assert summary["run_id"] == first_id
    assert summary["snapshot_id"] == f"snapshot_{first_id}"
    assert summary["snapshot_commit_sha"] == "a" * 40
    assert summary["fields_submitted"] == ["application_url"]
    assert second["optional_evidence"]["status"] == "not_submitted"


def test_optional_context_never_becomes_direct_repository_proof_or_automatic_score_change():
    run_id = _run_id()
    result = _persist_run(run_id)
    submitted = evidence.submit_mid_optional_evidence(
        run_id,
        {
            "token": result["optional_evidence_submission"]["token"],
            "architecture_documents": "Architecture notes supplied by the client.",
            "stakeholder_questionnaire": "Stakeholders prioritize reliability.",
            "business_priorities": "Budget and delivery constraints.",
        },
    )

    summary = submitted["optional_evidence"]
    assert summary["source_classification"] == "user_submitted_external_context"
    assert summary["verification_status"] == "human_review_required"
    assert summary["direct_repository_proof"] is False
    assert summary["score_change_allowed_without_review"] is False
    assert summary["section_availability"]["architecture_context"]["status"] == "human_review_required"
    assert summary["section_availability"]["stakeholder_alignment"]["status"] == "human_review_required"
    assert summary["section_availability"]["functional_qa"]["status"] == "unavailable"
    assert summary["section_availability"]["platform_parity"]["status"] == "unavailable"


def test_missing_optional_evidence_produces_truthful_unavailable_sections():
    run_id = _run_id()
    result = _persist_run(run_id)
    summary = result["optional_evidence"]

    assert summary["status"] == "not_submitted"
    assert summary["verification_status"] == "unavailable"
    assert summary["field_count"] == 0
    assert all(item["status"] == "unavailable" for item in summary["section_availability"].values())
    assert "requires a functioning application" in summary["section_availability"]["functional_qa"]["message"]
    assert "requires access" in summary["section_availability"]["platform_parity"]["message"]
    assert "require questionnaires" in summary["section_availability"]["stakeholder_alignment"]["message"]
    assert "requires goals" in summary["section_availability"]["business_roadmap"]["message"]


def test_invalid_url_field_and_total_limits_are_blocked_without_partial_write():
    run_id = _run_id()
    result = _persist_run(run_id)
    token = result["optional_evidence_submission"]["token"]

    invalid_url = evidence.submit_mid_optional_evidence(run_id, {"token": token, "application_url": "file:///local/app"})
    oversized = evidence.submit_mid_optional_evidence(run_id, {"token": token, "architecture_documents": "x" * (evidence.MAX_FIELD_CHARS + 1)})

    assert invalid_url["status"] == "blocked"
    assert "absolute http or https URL" in invalid_url["error"]
    assert oversized["status"] == "blocked"
    assert "character limit" in oversized["error"]
    assert evidence.optional_evidence_summary(run_id)["status"] == "not_submitted"


def test_expired_capability_returns_generic_not_found_and_does_not_write():
    run_id = _run_id()
    result = _persist_run(run_id)
    access = _access_record(run_id)
    access["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    STORE.put("evidence_items", access["evidence_id"], access)

    submitted = evidence.submit_mid_optional_evidence(
        run_id,
        {"token": result["optional_evidence_submission"]["token"], "application_url": "https://staging.example.com"},
    )

    assert submitted == {"status": "not_found", "error": "Optional evidence submission is unavailable."}
    assert evidence.optional_evidence_summary(run_id)["status"] == "not_submitted"


def test_repeated_submission_merges_fields_under_same_run_identity():
    run_id = _run_id()
    result = _persist_run(run_id)
    token = result["optional_evidence_submission"]["token"]

    first = evidence.submit_mid_optional_evidence(run_id, {"token": token, "application_url": "https://staging.example.com"})
    second = evidence.submit_mid_optional_evidence(run_id, {"token": token, "existing_roadmap": "Existing delivery roadmap."})

    assert first["idempotent_update"] is False
    assert second["idempotent_update"] is True
    assert second["optional_evidence"]["fields_submitted"] == ["application_url", "existing_roadmap"]
    stored = STORE.get("evidence_items", second["optional_evidence"]["evidence_id"])
    assert stored["submitted_evidence"]["application_url"] == "https://staging.example.com"
    assert stored["submitted_evidence"]["existing_roadmap"] == "Existing delivery roadmap."
    assert token not in repr(stored)


def test_api_returns_summary_and_uses_generic_errors():
    run_id = _run_id()
    result = _persist_run(run_id)
    response = mid_optional_evidence_response(
        run_id,
        MidOptionalEvidenceRequest(
            token=result["optional_evidence_submission"]["token"],
            product_requirements="The product must support authorized technical review.",
        ),
    )

    assert response["status"] == "submitted"
    assert response["optional_evidence"]["fields_submitted"] == ["product_requirements"]

    with pytest.raises(HTTPException) as invalid:
        mid_optional_evidence_response(
            run_id,
            MidOptionalEvidenceRequest(token="invalid", product_requirements="context"),
        )
    assert invalid.value.status_code == 404
    assert invalid.value.detail["message"] == "Optional evidence submission is unavailable."


def test_mid_status_persistence_attaches_summary_but_never_reissues_token():
    run_id = _run_id()
    initial = _persist_run(run_id)
    token = initial["optional_evidence_submission"]["token"]
    evidence.submit_mid_optional_evidence(run_id, {"token": token, "meeting_transcripts": "Bounded transcript summary."})

    refreshed_result = {
        "status": "running",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_optional",
        "project_id": "project_optional",
        "repository_snapshot": {
            "snapshot_id": f"snapshot_{run_id}",
            "commit_sha": "a" * 40,
        },
        "reports": {"pdf_base64": ""},
    }
    persist_mid_assessment_run(refreshed_result, {"run_id": run_id, "mode": "mid"})

    assert "optional_evidence_submission" not in refreshed_result
    assert refreshed_result["optional_evidence"]["status"] == "submitted"
    assert refreshed_result["optional_evidence"]["fields_submitted"] == ["meeting_transcripts"]
    assert token not in repr(STORE.get("assessment_runs", run_id))
