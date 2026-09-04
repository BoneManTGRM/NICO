from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from nico import specialist_access_v1 as access

# Existing non-Assessment API families that read or mutate client-linked records.
CLIENT_ROOTS = (
    "/reports", "/customers", "/projects", "/evidence", "/client-job",
    "/client-acceptance", "/approval", "/approvals", "/worker", "/retainer",
    "/max-target",
)
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")


@pytest.fixture
def guarded(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(access.SESSION_SIGNING_SECRET_ENV, "unit-test-signing-key-not-a-real-secret-0000")
    monkeypatch.setattr(access, "_RATE_LIMITER", access._BoundedRateLimiter())
    monkeypatch.setattr(
        access, "require_comprehensive_operator",
        lambda supplied: (supplied == "test-operator", {"authority": "nico_comprehensive_operator"}),
    )
    app = FastAPI()
    reached: list[str] = []

    async def client_record(request: Request):
        reached.append(request.url.path)
        return {"record": "test-only-confidential-record"}

    for root in CLIENT_ROOTS:
        app.add_api_route(root, client_record, methods=list(METHODS))
        app.add_api_route(root + "/{record_id}", client_record, methods=list(METHODS))
    app.add_api_route("/assessment/comprehensive-run/{run_id}/report/json", client_record, methods=["GET"])
    app.add_api_route("/health", lambda: {"status": "ok"}, methods=["GET"])
    app.add_api_route("/delivery/approved/inspect", lambda: {"token_required": True}, methods=["POST"])
    access.install_specialist_access(app)
    with TestClient(app) as client:
        yield client, reached


@pytest.mark.parametrize("root", CLIENT_ROOTS)
@pytest.mark.parametrize("method", METHODS)
def test_anonymous_client_routes_do_not_reach_storage(guarded, root, method):
    client, reached = guarded
    for suffix in ("", "/existing", "/missing"):
        response = client.request(method, root + suffix)
        assert response.status_code == 401
        assert "no-store" in response.headers["cache-control"]
        assert "test-only-confidential-record" not in response.text
    assert reached == []


@pytest.mark.parametrize("root", CLIENT_ROOTS)
def test_invalid_or_expired_sessions_cannot_read_client_records(guarded, root):
    client, reached = guarded
    expired, _ = access.issue_specialist_session({"authority": "nico_comprehensive_operator"}, now=1)
    for token in ("invalid", expired):
        response = client.get(root + "/existing", headers={"X-NICO-Operator-Session": token})
        assert response.status_code == 401
    assert reached == []


@pytest.mark.parametrize("root", CLIENT_ROOTS)
def test_authenticated_specialist_read_still_works(guarded, root):
    client, reached = guarded
    token, _ = access.issue_specialist_session({"authority": "nico_comprehensive_operator"})
    response = client.get(root + "/existing", headers={"X-NICO-Operator-Session": token})
    assert response.status_code == 200
    assert response.json()["record"] == "test-only-confidential-record"
    assert "private" in response.headers["cache-control"]
    assert reached == [root + "/existing"]


@pytest.mark.parametrize("role", ("producer", "consumer"))
def test_ci_proof_sessions_cannot_access_client_data_families(guarded, role):
    client, reached = guarded
    token, _ = access.issue_specialist_session(
        {"authority": "github_actions_production_proof"}, scope=access.PRODUCTION_PROOF_SCOPE,
        retained_claims={
            "repository": "BoneManTGRM/NICO", "ref": "refs/heads/main", "sha": "a" * 40,
            "workflow_ref": "test-workflow", "run_id": "100", "run_attempt": "1",
            "proof_role": role,
        },
    )
    headers = {"X-NICO-Operator-Session": token}
    for root in CLIENT_ROOTS:
        for method in ("GET", "POST"):
            response = client.request(method, root + "/existing", headers=headers)
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "production_proof_session_scope_forbidden"
    assert reached == []
    allowed = client.get("/assessment/comprehensive-run/test/report/json", headers=headers)
    assert allowed.status_code == 200


def test_health_login_and_token_delivery_protocols_are_unchanged(guarded):
    client, _ = guarded
    assert client.get("/health").status_code == 200
    assert client.post("/delivery/approved/inspect").json() == {"token_required": True}
    assert client.post(access.SESSION_ROUTE).status_code == 403
    login = client.post(access.SESSION_ROUTE, headers={"X-NICO-Admin-Token": "test-operator"})
    assert login.status_code == 200
    assert access.validate_specialist_session(login.json()["session_token"]) is not None


def test_root_matching_has_segment_boundaries():
    for path in ("/reports-public", "/projects-public", "/evidence-policy", "/report-templates"):
        assert access._protected_request(path) is False
    for root in CLIENT_ROOTS:
        assert access._protected_request(root)
        assert access._protected_request(root + "/")
        assert access._protected_request(root + "/any/child")
