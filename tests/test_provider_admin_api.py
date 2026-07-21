from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.provider_admin_api import (
    HeaderAdminAuthorizer,
    ProviderAdminRuntime,
    register_provider_admin_routes,
)
from nico.provider_credential_rotation import CredentialRotationLedger, CredentialRotationPolicy
from nico.provider_credentials import SecretValue
from nico.provider_neutral_contract import ProviderKind
from nico.provider_work_items import CanonicalWorkItem, WorkItemCollection


def _runtime(path: Path) -> ProviderAdminRuntime:
    ledger = CredentialRotationLedger(lambda: sqlite3.connect(path), dialect="sqlite")
    ledger.ensure_schema()

    def collect(repository_id: str, options):
        del options
        return WorkItemCollection(
            provider=ProviderKind.GITLAB,
            project_id="group/repo",
            repository_id=repository_id,
            items=(
                CanonicalWorkItem(
                    provider=ProviderKind.GITLAB,
                    native_id="7",
                    project_id="group/repo",
                    repository_id=repository_id,
                    item_type="issue",
                    title="Repair issue",
                    state="opened",
                    assignee="dev",
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-02T00:00:00Z",
                    url="https://gitlab.example.com/issues/7",
                    source_fingerprint="sha256:finding",
                ),
            ),
            collected_at="2026-07-21T00:00:00Z",
            requests_made=2,
            pages_fetched=1,
        )

    return ProviderAdminRuntime(
        authorizer=HeaderAdminAuthorizer(SecretValue("admin-secret")),
        credential_ledger=ledger,
        rotation_policy=CredentialRotationPolicy(max_age_days=90),
        work_item_collectors={ProviderKind.GITLAB: collect},
    )


def _client(path: Path) -> TestClient:
    app = FastAPI()
    register_provider_admin_routes(app, runtime=_runtime(path))
    return TestClient(app)


def _headers():
    return {"X-NICO-Admin-Token": "admin-secret"}


def test_admin_authorization_is_required_and_secret_is_not_returned(tmp_path: Path) -> None:
    client = _client(tmp_path / "admin.db")
    denied = client.post("/admin/providers/gitlab/work-items/17/collect", json={})
    allowed = client.post(
        "/admin/providers/gitlab/work-items/17/collect",
        json={},
        headers=_headers(),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["item_count"] == 1
    assert allowed.json()["items"][0]["native_id"] == "7"
    assert allowed.json()["read_only"] is True
    assert allowed.json()["client_delivery_allowed"] is False
    assert "admin-secret" not in str(allowed.json())


def test_credential_activation_listing_and_retirement_expose_only_references(tmp_path: Path) -> None:
    client = _client(tmp_path / "rotation.db")
    activated = client.post(
        "/admin/providers/gitlab/credentials/gitlab-prod/activate",
        headers=_headers(),
        json={
            "version": "v1",
            "secret_reference": "NICO_GITLAB_TOKEN_V1",
            "activated_by": "operator",
            "approved_by": "security-approver",
            "activated_at": "2026-07-21T00:00:00Z",
            "expires_at": "2026-08-20T00:00:00Z",
        },
    )
    listed = client.get(
        "/admin/providers/gitlab/credentials/gitlab-prod/versions",
        headers=_headers(),
    )
    retired = client.post(
        "/admin/providers/gitlab/credentials/gitlab-prod/retire",
        headers=_headers(),
        json={
            "version": "v1",
            "retired_by": "security-approver",
            "retired_at": "2026-07-22T00:00:00Z",
        },
    )

    assert activated.status_code == 200
    assert activated.json()["credential"]["secret_reference"] == "NICO_GITLAB_TOKEN_V1"
    assert activated.json()["credential"]["raw_secret_present"] is False
    assert listed.status_code == 200
    assert len(listed.json()["versions"]) == 1
    assert listed.json()["raw_secret_present"] is False
    assert retired.status_code == 200
    assert retired.json()["credential"]["status"] == "retired"
    rendered = str((activated.json(), listed.json(), retired.json()))
    assert "raw-secret-value" not in rendered
    assert "admin-secret" not in rendered


def test_activation_rejects_raw_secret_fields_and_same_actor_approval(tmp_path: Path) -> None:
    client = _client(tmp_path / "invalid.db")
    raw = client.post(
        "/admin/providers/gitlab/credentials/gitlab-prod/activate",
        headers=_headers(),
        json={
            "version": "v1",
            "secret_reference": "NICO_GITLAB_TOKEN_V1",
            "secret": "raw-secret-value",
            "activated_by": "operator",
            "approved_by": "approver",
        },
    )
    same_actor = client.post(
        "/admin/providers/gitlab/credentials/gitlab-prod/activate",
        headers=_headers(),
        json={
            "version": "v1",
            "secret_reference": "NICO_GITLAB_TOKEN_V1",
            "activated_by": "same-user",
            "approved_by": "same-user",
        },
    )

    assert raw.status_code == 422
    assert raw.json()["detail"] == "credential_activation_fields_invalid"
    assert same_actor.status_code == 422
    assert same_actor.json()["detail"] == "credential_rotation_dual_control_required"


def test_missing_collector_and_provider_mismatch_fail_closed(tmp_path: Path) -> None:
    client = _client(tmp_path / "missing.db")
    missing = client.post(
        "/admin/providers/bitbucket/work-items/workspace/repo/collect",
        headers=_headers(),
        json={},
    )
    unsupported = client.post(
        "/admin/providers/unknown/work-items/repo/collect",
        headers=_headers(),
        json={},
    )

    assert missing.status_code == 422
    assert missing.json()["detail"] == "provider_work_item_collector_not_configured"
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"] == "provider_not_supported"


def test_route_registration_is_idempotent_and_partial_groups_fail(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "routes.db")
    app = FastAPI()
    register_provider_admin_routes(app, runtime=runtime)
    count = len(app.routes)
    register_provider_admin_routes(app, runtime=runtime)
    assert len(app.routes) == count

    partial = FastAPI()

    @partial.get("/admin/providers/{provider}/credentials/{key_id}/versions")
    async def existing():
        return {}

    try:
        register_provider_admin_routes(partial, runtime=runtime)
    except RuntimeError as exc:
        assert str(exc) == "provider_admin_partial_route_group_detected"
    else:
        raise AssertionError("partial provider admin route group should fail")
