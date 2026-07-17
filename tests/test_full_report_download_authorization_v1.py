from __future__ import annotations

from nico.full_report_download_authorization_v1 import (
    attach_full_download_authorization,
    authorize_full_download,
)


def _response() -> dict:
    return {
        "client_delivery_allowed": True,
        "artifact": {
            "artifact_id": "artifact-full-pdf-1",
            "sha256": "a" * 64,
            "filename": "nico-full-report.pdf",
        },
    }


def test_authorized_download_creates_deterministic_allow_audit_event() -> None:
    first = authorize_full_download(
        _response(),
        actor_id="user-1",
        actor_role="client_reviewer",
        workspace_id="workspace-1",
        assessment_workspace_id="workspace-1",
        request_id="request-1",
    )
    second = authorize_full_download(
        _response(),
        actor_id="user-1",
        actor_role="client_reviewer",
        workspace_id="workspace-1",
        assessment_workspace_id="workspace-1",
        request_id="request-1",
    )

    assert first["status"] == "authorized"
    assert first["client_delivery_allowed"] is True
    assert first["audit_event"]["decision"] == "allow"
    assert first["audit_event"]["audit_event_id"] == second["audit_event"]["audit_event_id"]
    assert first["response"] is not None


def test_workspace_mismatch_fails_closed_and_records_denial() -> None:
    decision = authorize_full_download(
        _response(),
        actor_id="user-1",
        actor_role="admin",
        workspace_id="workspace-a",
        assessment_workspace_id="workspace-b",
        request_id="request-2",
    )

    assert decision["status"] == "blocked"
    assert decision["client_delivery_allowed"] is False
    assert "workspace_identity_mismatch" in decision["issues"]
    assert decision["audit_event"]["decision"] == "deny"
    assert decision["response"] is None


def test_unapproved_role_and_response_are_blocked() -> None:
    response = _response()
    response["client_delivery_allowed"] = False
    decision = authorize_full_download(
        response,
        actor_id="user-2",
        actor_role="viewer",
        workspace_id="workspace-1",
        assessment_workspace_id="workspace-1",
        request_id="request-3",
    )

    assert "role_not_authorized" in decision["issues"]
    assert "download_response_not_approved" in decision["issues"]
    assert decision["client_delivery_allowed"] is False


def test_missing_identity_and_artifact_proof_are_blocked() -> None:
    decision = authorize_full_download(
        {"client_delivery_allowed": True, "artifact": {}},
        actor_id="",
        actor_role="owner",
        workspace_id="",
        assessment_workspace_id="",
        request_id="",
    )

    assert set(decision["issues"]) >= {
        "missing_actor_id",
        "missing_workspace_identity",
        "missing_request_id",
        "missing_artifact_id",
        "missing_artifact_checksum",
    }


def test_attach_preserves_existing_delivery_block() -> None:
    result = {
        "client_delivery_allowed": False,
        "full_download_response": _response(),
    }
    attached = attach_full_download_authorization(
        result,
        actor_id="owner-1",
        actor_role="owner",
        workspace_id="workspace-1",
        assessment_workspace_id="workspace-1",
        request_id="request-4",
    )

    assert attached["full_download_authorization"]["client_delivery_allowed"] is True
    assert attached["client_delivery_allowed"] is False
