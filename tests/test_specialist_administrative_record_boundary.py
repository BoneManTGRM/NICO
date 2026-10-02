"""Reject alternate operational-record retrieval before touching any tenant's store.

All identities and credentials below are synthetic. The existing directory
contract is global site administration; a Comprehensive session is not an
authenticated customer identity and cannot grant tenant access by query/header.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import nico.specialist_access_v1 as access

ADMIN = "test-only-administrator-record-boundary"
OPERATOR = "test-only-comprehensive-record-boundary"
LEGACY_OPERATOR = "test-only-legacy-record-boundary"
RECORD_PATHS = (
    "/customers", "/customers/synthetic-b", "/projects",
    "/projects/synthetic-b", "/projects/synthetic-b/runs",
    "/projects/synthetic-b/latest", "/projects/synthetic-b/trends",
    "/projects/synthetic-b/reports", "/projects/synthetic-b/approvals",
    "/projects/synthetic-b/evidence", "/evidence/synthetic-b",
    "/scans/latest", "/findings", "/findings/synthetic-b", "/drift",
    "/repairs", "/verification/latest", "/memory", "/audit-log",
    "/approvals", "/client-acceptance/synthetic-b",
)


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", OPERATOR)
    monkeypatch.setenv("NICO_SARA_OPERATOR_PASSWORD", LEGACY_OPERATOR)
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "test-only-record-boundary-signing-secret-at-least-32-bytes",
    )
    monkeypatch.setattr(access, "_RATE_LIMITER", type(access._RATE_LIMITER)())
    specialist, _ = access.issue_specialist_session(
        {"authority": "nico_comprehensive_operator"}
    )
    reduced_admin, _ = access.issue_specialist_session({"authority": "nico_admin"})
    proof, _ = access.issue_specialist_session(
        {"authority": "github_actions"},
        scope=access.PRODUCTION_PROOF_SCOPE,
        retained_claims={
            "repository": "synthetic/nico",
            "ref": "refs/heads/main",
            "sha": "a" * 40,
            "workflow_ref": "synthetic/nico/.github/workflows/test.yml@refs/heads/main",
            "run_id": "123",
            "run_attempt": "1",
            "proof_role": "consumer",
        },
    )
    return {
        "anonymous": {},
        "wrong_admin": {"X-NICO-Admin-Token": "test-only-wrong-administrator"},
        "operator": {"X-NICO-Admin-Token": OPERATOR},
        "legacy_operator": {"X-NICO-Admin-Token": LEGACY_OPERATOR},
        "specialist_session": {"X-NICO-Operator-Session": specialist},
        "reduced_admin_session": {"X-NICO-Operator-Session": reduced_admin},
        "production_proof": {"X-NICO-Operator-Session": proof},
        "administrator": {"X-NICO-Admin-Token": ADMIN},
    }


def record_app():
    app = FastAPI()
    reads = []

    async def record(request: Request):
        reads.append(request.url.path)
        return {"private_marker": "synthetic-tenant-b-report"}

    for path in RECORD_PATHS:
        app.add_api_route(path, record, methods=["GET"])
    app.add_api_route("/evidence/upload", record, methods=["POST"])
    app.add_api_route("/approval/create", record, methods=["POST"])
    app.add_api_route("/client-acceptance/synthetic-b/approved", record, methods=["POST"])
    app.add_api_route("/scan/local", record, methods=["POST"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/assessment/comprehensive-run/synthetic-a")
    def owned_assessment():
        return {"run_id": "synthetic-a"}

    access.install_specialist_access(app)
    return app, reads


@pytest.mark.parametrize("path", RECORD_PATHS)
@pytest.mark.parametrize(
    "credential",
    [
        "anonymous", "wrong_admin", "operator", "legacy_operator",
        "specialist_session", "reduced_admin_session", "production_proof",
    ],
)
def test_private_directory_rejects_lower_authority_before_store(
    credentials, path, credential,
):
    app, reads = record_app()
    with TestClient(app) as client:
        response = client.get(
            path + "?customer_id=synthetic-a&project_id=synthetic-a&role=owner",
            headers={
                **credentials[credential],
                "X-NICO-Customer-ID": "synthetic-a",
                "X-NICO-Project-ID": "synthetic-a",
            },
        )
    assert response.status_code == (401 if credential == "anonymous" else 403)
    assert response.json()["detail"]["code"] == "site_admin_authentication_required"
    assert response.headers["Cache-Control"] == "no-store"
    assert "synthetic-tenant-b-report" not in response.text
    assert reads == []


@pytest.mark.parametrize("path", RECORD_PATHS)
def test_existing_global_administrator_retains_directory_access(credentials, path):
    app, reads = record_app()
    with TestClient(app) as client:
        response = client.get(path, headers=credentials["administrator"])
    assert response.status_code == 200
    assert response.json()["private_marker"] == "synthetic-tenant-b-report"
    assert reads == [path]
    assert response.headers["Cache-Control"] == "no-store, private, max-age=0"


@pytest.mark.parametrize(
    "path",
    [
        "/evidence/upload", "/approval/create",
        "/client-acceptance/synthetic-b/approved", "/scan/local",
    ],
)
def test_alternate_record_writes_share_the_administrator_boundary(credentials, path):
    app, reads = record_app()
    with TestClient(app) as client:
        blocked = client.post(path, headers=credentials["specialist_session"], json={})
        assert blocked.status_code == 403
        assert reads == []
        allowed = client.post(path, headers=credentials["administrator"], json={})
    assert allowed.status_code == 200
    assert reads == [path]


def test_specialist_assessment_and_public_health_contract_remain_valid(credentials):
    app, reads = record_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        allowed = client.get(
            "/assessment/comprehensive-run/synthetic-a",
            headers=credentials["specialist_session"],
        )
    assert allowed.status_code == 200
    assert allowed.json()["run_id"] == "synthetic-a"
    assert reads == []


@pytest.mark.parametrize("path", ["/projects", "/projects/synthetic-b/reports"])
def test_unconfigured_site_administration_remains_closed(
    credentials, monkeypatch, path,
):
    monkeypatch.delenv("NICO_ADMIN_TOKEN")
    app, reads = record_app()
    with TestClient(app) as client:
        response = client.get(path, headers=credentials["administrator"])
    assert response.status_code == 403
    assert reads == []


def test_final_production_app_blocks_alternate_report_retrieval_before_query(
    credentials, monkeypatch,
):
    from nico.api.specialist_ship_ready_bootstrap import app
    import nico.api.main as main

    reads = []

    def synthetic_reports(project_id):
        reads.append(project_id)
        return {"project_id": project_id, "private_marker": "synthetic-tenant-b-report"}

    monkeypatch.setattr(main, "project_reports", synthetic_reports)
    with TestClient(app) as client:
        path = "/projects/synthetic-b/reports"
        for name in ["anonymous", "operator", "specialist_session", "production_proof"]:
            response = client.get(path, headers=credentials[name])
            assert response.status_code in {401, 403}
            assert "synthetic-tenant-b-report" not in response.text
        assert reads == []
        allowed = client.get(path, headers=credentials["administrator"])
    assert allowed.status_code == 200
    assert reads == ["synthetic-b"]
    assert allowed.json()["private_marker"] == "synthetic-tenant-b-report"

@pytest.mark.parametrize(
    "path,payload,handler",
    [
        ("/scan/local", {"path": "."}, "run_scan"),
        (
            "/client-acceptance/synthetic-b/approved",
            {"actor": "synthetic-test-actor"},
            "transition_client_acceptance",
        ),
    ],
)
def test_final_app_blocks_legacy_mutation_before_local_scan_or_acceptance(
    credentials, monkeypatch, path, payload, handler,
):
    from nico.api.specialist_ship_ready_bootstrap import app
    import nico.api.main as main

    mutations = []

    def synthetic_mutator(*args, **kwargs):
        mutations.append((args, kwargs))
        # No scan, approval, report or delivery record is changed by this spy.
        return {"status": "guard_verified", "client_delivery_allowed": False}

    monkeypatch.setattr(main, handler, synthetic_mutator)
    with TestClient(app) as client:
        for name in ["anonymous", "operator", "specialist_session", "production_proof"]:
            response = client.post(path, headers=credentials[name], json=payload)
            assert response.status_code in {401, 403}
        assert mutations == []
        allowed = client.post(path, headers=credentials["administrator"], json=payload)
    assert allowed.status_code == 200
    assert len(mutations) == 1
    assert allowed.json()["client_delivery_allowed"] is False


def test_local_host_guard_does_not_reclassify_demonstration_scan_paths():
    assert access._administrative_record_request("/scan/local") is True
    assert access._administrative_record_request("/scan/test-lab") is False
    assert access._administrative_record_request("/scan/drift-demo") is False
