from __future__ import annotations

from nico.decision_grade_accepted_edition_v2 import build_accepted_report_edition


BASE = {
    "repository": "owner/repo",
    "commit_sha": "a" * 40,
    "tree_sha": "b" * 40,
    "run_id": "run-1",
    "scanner_run_id": "scan-1",
    "evidence_bundle_hash": "c" * 64,
    "report_language": "en",
    "assessment_depth": "strategic",
    "artifacts": {
        "markdown": "# Report",
        "html": "<h1>Report</h1>",
        "pdf": b"%PDF-1.7 test",
        "json": {"status": "final"},
    },
    "reviewer": "reviewer@example.com",
    "reviewer_role": "Independent technical reviewer",
    "decision": "approved",
    "decision_reason": "Evidence and report package accepted.",
    "decided_at": "2026-07-25T22:30:00+00:00",
}


def test_approved_complete_edition_allows_delivery() -> None:
    result = build_accepted_report_edition(**BASE)

    assert result["accepted_edition"] is True
    assert result["client_delivery_allowed"] is True
    assert result["delivery_status"] == "approved_for_delivery"
    assert result["validation_errors"] == []
    assert set(result["artifact_digests"]) == {
        "markdown",
        "html",
        "pdf",
        "json",
    }
    assert len(result["review"]["approval_certificate_sha256"]) == 64


def test_missing_artifact_blocks_approval() -> None:
    values = dict(BASE)
    values["artifacts"] = {
        key: value for key, value in BASE["artifacts"].items() if key != "pdf"
    }

    result = build_accepted_report_edition(**values)

    assert result["accepted_edition"] is False
    assert result["client_delivery_allowed"] is False
    assert "missing_required_artifacts:pdf" in result["validation_errors"]


def test_rejection_never_allows_delivery() -> None:
    values = dict(
        BASE,
        decision="rejected",
        decision_reason="Residual risk was not accepted.",
    )
    result = build_accepted_report_edition(**values)

    assert result["accepted_edition"] is False
    assert result["delivery_status"] == "blocked"
    assert result["review"]["decision"] == "rejected"


def test_request_more_evidence_never_allows_delivery() -> None:
    values = dict(
        BASE,
        decision="request_more_evidence",
        decision_reason="Scanner evidence is incomplete.",
    )
    result = build_accepted_report_edition(**values)

    assert result["accepted_edition"] is False
    assert result["client_delivery_allowed"] is False
    assert result["review"]["decision"] == "request_more_evidence"


def test_missing_identity_and_reviewer_fields_fail_closed() -> None:
    values = dict(BASE, commit_sha="", reviewer="", reviewer_role="")
    result = build_accepted_report_edition(**values)

    assert "missing_identity:commit_sha" in result["validation_errors"]
    assert "missing_reviewer" in result["validation_errors"]
    assert "missing_reviewer_role" in result["validation_errors"]
    assert result["client_delivery_allowed"] is False


def test_manifest_is_deterministic_with_fixed_time() -> None:
    first = build_accepted_report_edition(**BASE)
    second = build_accepted_report_edition(**BASE)

    assert first == second
    assert len(first["accepted_edition_manifest_sha256"]) == 64
    assert len(first["report_artifact_digest"]) == 64


def test_artifact_digest_changes_when_report_changes() -> None:
    first = build_accepted_report_edition(**BASE)
    values = dict(BASE)
    values["artifacts"] = {**BASE["artifacts"], "markdown": "# Changed"}
    second = build_accepted_report_edition(**values)

    assert first["report_artifact_digest"] != second["report_artifact_digest"]
    assert (
        first["review"]["approval_certificate_sha256"]
        != second["review"]["approval_certificate_sha256"]
    )
