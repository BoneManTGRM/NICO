from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import ssl
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.github_actions_proof_auth_v1 import (
    CONSUMER_WORKFLOW_PATHS,
    CONSUMER_ENVIRONMENT,
    RECOVERY_WORKFLOW_PATHS,
    expected_release_sha,
    validate_github_actions_claims,
)
from nico.specialist_access_v1 import (
    GITHUB_ACTIONS_SESSION_ROUTE,
    PRODUCTION_PROOF_SCOPE,
    install_specialist_access,
    issue_specialist_session,
    validate_specialist_session,
)
from scripts.github_actions_nico_proof_auth_v1 import AuthenticatedBrowser
from scripts import github_actions_nico_proof_auth_v1 as proof_auth


SHA = "a" * 40
WORKFLOW_REF = (
    "BoneManTGRM/NICO/.github/workflows/"
    "spanish-comprehensive-production-proof.yml@refs/heads/main"
)

CLAIMS = {
    "repository": "BoneManTGRM/NICO",
    "ref": "refs/heads/main",
    "sha": SHA,
    "event_name": "push",
    "sub": "repo:BoneManTGRM/NICO:ref:refs/heads/main",
    "workflow_ref": WORKFLOW_REF,
    "run_id": "33899900001",
    "run_attempt": "1",
    "actor": "BoneManTGRM",
}



def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/assessment/comprehensive-intake")
    def intake() -> dict[str, str]:
        return {"status": "started"}

    @app.get("/assessment/comprehensive-run/{run_id}")
    def status(run_id: str) -> dict[str, str]:
        return {"status": "running", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/continue")
    def continuation(run_id: str) -> dict[str, str]:
        return {"status": "running", "run_id": run_id}

    @app.get("/assessment/comprehensive-run/{run_id}/report/json")
    def report(run_id: str) -> dict[str, str]:
        return {"status": "draft", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/review")
    def review(run_id: str) -> dict[str, str]:
        return {"status": "approved", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/authorize-delivery")
    def authorize_delivery(run_id: str) -> dict[str, str]:
        return {"status": "authorized", "run_id": run_id}

    @app.get("/assessment/comprehensive-run/{run_id}/approved-delivery-package")
    def approved_delivery(run_id: str) -> dict[str, str]:
        return {"status": "client_final", "run_id": run_id}

    @app.post("/assessment/comprehensive-run/{run_id}/automated-delivery-package")
    def automated_delivery(run_id: str) -> dict[str, str]:
        return {"status": "automated", "run_id": run_id}

    install_specialist_access(app)
    return app


def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "test-signing-secret-with-at-least-thirty-two-bytes",
    )
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", SHA)


def test_railway_deployed_sha_overrides_stale_manual_release_pin(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", SHA)
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "b" * 40)

    assert expected_release_sha() == SHA
    assert validate_github_actions_claims(CLAIMS)["sha"] == SHA


def test_manual_release_sha_remains_non_railway_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", SHA)

    assert expected_release_sha() == SHA


def test_present_invalid_railway_release_sha_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "not-a-sha")
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", SHA)

    with pytest.raises(ValueError, match="github_actions_proof_railway_release_sha_invalid"):
        expected_release_sha()


def test_exact_github_actions_claims_are_required(monkeypatch: pytest.MonkeyPatch):
    _environment(monkeypatch)
    accepted = validate_github_actions_claims(CLAIMS)
    assert accepted["sha"] == SHA
    assert accepted["workflow_ref"] == WORKFLOW_REF

    for field, wrong in (
        ("repository", "other/repo"),
        ("ref", "refs/heads/feature"),
        ("sha", "b" * 40),
        ("event_name", "pull_request"),
        ("workflow_ref", "BoneManTGRM/NICO/.github/workflows/other.yml@refs/heads/main"),
        ("run_id", "not-a-run"),
    ):
        candidate = {**CLAIMS, field: wrong}
        with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch"):
            validate_github_actions_claims(candidate)


@pytest.mark.parametrize("workflow_path", sorted(CONSUMER_WORKFLOW_PATHS))
def test_only_exact_environment_bound_consumers_are_accepted(monkeypatch, workflow_path):
    _environment(monkeypatch)
    claims = {
        **CLAIMS,
        "event_name": "workflow_run",
        "environment": CONSUMER_ENVIRONMENT,
        "sub": f"repo:BoneManTGRM/NICO:environment:{CONSUMER_ENVIRONMENT}",
        "workflow_ref": f"BoneManTGRM/NICO/{workflow_path}@refs/heads/main",
    }
    accepted = validate_github_actions_claims(claims)
    assert accepted["proof_role"] == "consumer"
    assert accepted["sha"] == SHA
    for field, wrong in (
        ("repository", "other/repo"), ("ref", "refs/heads/feature"),
        ("sha", "b" * 40), ("environment", "production"),
        ("sub", CLAIMS["sub"]), ("event_name", "pull_request"),
        ("event_name", "push"), ("run_attempt", "0"),
        ("workflow_ref", "BoneManTGRM/NICO/.github/workflows/untrusted.yml@refs/heads/main"),
    ):
        with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch"):
            validate_github_actions_claims({**claims, field: wrong})
    with pytest.raises(ValueError, match="environment"):
        validate_github_actions_claims({k: v for k, v in claims.items() if k != "environment"})




@pytest.mark.parametrize("workflow_path", sorted(RECOVERY_WORKFLOW_PATHS))
def test_only_exact_environment_bound_recovery_workflow_is_accepted(
    monkeypatch, workflow_path
):
    _environment(monkeypatch)
    claims = {
        **CLAIMS,
        "event_name": "push",
        "environment": CONSUMER_ENVIRONMENT,
        "sub": f"repo:BoneManTGRM/NICO:environment:{CONSUMER_ENVIRONMENT}",
        "workflow_ref": f"BoneManTGRM/NICO/{workflow_path}@refs/heads/main",
    }
    accepted = validate_github_actions_claims(claims)
    assert accepted["proof_role"] == "recovery"
    assert accepted["sha"] == SHA
    for field, wrong in (
        ("repository", "other/repo"),
        ("ref", "refs/heads/feature"),
        ("sha", "b" * 40),
        ("environment", "production"),
        ("sub", CLAIMS["sub"]),
        ("event_name", "workflow_run"),
        ("event_name", "pull_request"),
        ("run_attempt", "0"),
        ("workflow_ref", "BoneManTGRM/NICO/.github/workflows/untrusted.yml@refs/heads/main"),
    ):
        with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch"):
            validate_github_actions_claims({**claims, field: wrong})


def test_recovery_session_can_only_read_and_continue_preserved_run(monkeypatch):
    _environment(monkeypatch)
    token, _ = issue_specialist_session(
        {"authority": "github_actions_production_proof"},
        scope=PRODUCTION_PROOF_SCOPE,
        retained_claims={**CLAIMS, "proof_role": "recovery"},
    )
    client = TestClient(_app())
    headers = {"X-NICO-Operator-Session": token}
    assert client.get("/assessment/comprehensive-run/comprun_test", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test/report/json", headers=headers).status_code == 200
    assert client.post("/assessment/comprehensive-run/comprun_test/continue", headers=headers).status_code == 200
    for path in (
        "/assessment/comprehensive-intake",
        "/assessment/comprehensive-run/comprun_test/review",
        "/assessment/comprehensive-run/comprun_test/authorize-delivery",
    ):
        assert client.post(path, headers=headers).status_code == 403
    assert client.get(
        "/assessment/comprehensive-run/comprun_test/approved-delivery-package",
        headers=headers,
    ).status_code == 403


def test_retired_finalizer_identity_is_not_accepted(monkeypatch):
    _environment(monkeypatch)
    with pytest.raises(ValueError, match="github_actions_oidc_claim_mismatch"):
        validate_github_actions_claims({
            **CLAIMS, "event_name": "workflow_run",
            "workflow_ref": "BoneManTGRM/NICO/.github/workflows/specialist-production-proof-finalizer.yml@refs/heads/main",
        })


def test_consumer_session_cannot_start_continue_review_or_deliver(monkeypatch):
    _environment(monkeypatch)
    token, _ = issue_specialist_session(
        {"authority": "github_actions_production_proof"},
        scope=PRODUCTION_PROOF_SCOPE,
        retained_claims={**CLAIMS, "proof_role": "consumer"},
    )
    client = TestClient(_app())
    headers = {"X-NICO-Operator-Session": token}
    assert client.get("/assessment/comprehensive-run/comprun_test", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test/report/json", headers=headers).status_code == 200
    for path in (
        "/assessment/comprehensive-intake",
        "/assessment/comprehensive-run/comprun_test/continue",
        "/assessment/comprehensive-run/comprun_test/review",
        "/assessment/comprehensive-run/comprun_test/authorize-delivery",
    ):
        assert client.post(path, headers=headers).status_code == 403
    assert client.get("/assessment/comprehensive-run/comprun_test/approved-delivery-package", headers=headers).status_code == 403


def test_production_proof_session_can_scan_but_cannot_approve_or_deliver(
    monkeypatch: pytest.MonkeyPatch,
):
    _environment(monkeypatch)
    token, _ = issue_specialist_session(
        {"authority": "github_actions_production_proof"},
        scope=PRODUCTION_PROOF_SCOPE,
        ttl_seconds=10_800,
        retained_claims=CLAIMS,
    )
    assert validate_specialist_session(token)["scope"] == PRODUCTION_PROOF_SCOPE
    client = TestClient(_app())
    headers = {"X-NICO-Operator-Session": token}

    assert client.post("/assessment/comprehensive-intake", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test", headers=headers).status_code == 200
    assert client.post("/assessment/comprehensive-run/comprun_test/continue", headers=headers).status_code == 200
    assert client.get("/assessment/comprehensive-run/comprun_test/report/json", headers=headers).status_code == 200

    protected_actions = (
        ("post", "/assessment/comprehensive-run/comprun_test/review"),
        ("post", "/assessment/comprehensive-run/comprun_test/authorize-delivery"),
        ("get", "/assessment/comprehensive-run/comprun_test/approved-delivery-package"),
        ("post", "/assessment/comprehensive-run/comprun_test/automated-delivery-package"),
    )
    for method, path in protected_actions:
        forbidden = getattr(client, method)(path, headers=headers)
        assert forbidden.status_code == 403
        assert (
            forbidden.json()["detail"]["code"]
            == "production_proof_session_scope_forbidden"
        )


def test_oidc_exchange_issues_only_restricted_session(monkeypatch: pytest.MonkeyPatch):
    _environment(monkeypatch)
    monkeypatch.setattr(
        "nico.specialist_access_v1.verify_github_actions_oidc_token",
        lambda _token: dict(CLAIMS),
    )
    client = TestClient(_app())
    response = client.post(
        GITHUB_ACTIONS_SESSION_ROUTE,
        headers={"Authorization": "Bearer cryptographically-verified-by-test-double"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == PRODUCTION_PROOF_SCOPE
    assert payload["release_sha"] == SHA
    assert payload["workflow_ref"] == WORKFLOW_REF
    session = validate_specialist_session(payload["session_token"])
    assert session is not None
    assert session["scope"] == PRODUCTION_PROOF_SCOPE
    assert session["sha"] == SHA


class _FakeContext:
    def __init__(self) -> None:
        self.cookies: list[dict[str, object]] = []

    def add_cookies(self, cookies):
        self.cookies.extend(cookies)


class _FakeBrowser:
    def __init__(self) -> None:
        self.kwargs = None
        self.context = _FakeContext()

    def new_context(self, *args, **kwargs):
        self.kwargs = kwargs
        return self.context


def test_browser_auth_is_cookie_scoped_and_never_global_header():
    raw = _FakeBrowser()
    wrapped = AuthenticatedBrowser(
        raw,
        session="scoped-session-token",
        frontend_url="https://app.nicoaudit.com",
    )
    wrapped.new_context(extra_http_headers={"Cache-Control": "no-store"})
    assert raw.kwargs == {"extra_http_headers": {"Cache-Control": "no-store"}}
    assert raw.context.cookies == [
        {
            "name": "nico-specialist-session",
            "value": "scoped-session-token",
            "url": "https://app.nicoaudit.com",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Strict",
        }
    ]


# Synthetic credentials deliberately appear in exception messages/bodies/URLs so
# formatted tracebacks and captured output can be checked for accidental leaks.
_PRIVATE = "synthetic-oidc-private"
_OIDC_URL = "https://oidc.invalid/token?ephemeral=" + _PRIVATE
_FRONTEND = "https://frontend.invalid"


def _json_response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def _http_error(status):
    return urllib.error.HTTPError(
        _OIDC_URL, status, _PRIVATE, {}, io.BytesIO(_PRIVATE.encode())
    )


@pytest.fixture
def acquisition(monkeypatch):
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", _OIDC_URL)
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", _PRIVATE)
    monkeypatch.setenv("RELEASE_SHA", SHA)
    monkeypatch.delenv("NICO_GITHUB_ACTIONS_OIDC_AUDIENCE", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    monkeypatch.setattr(proof_auth, "_PROOF_SECRETS", set())
    clock = SimpleNamespace(now=0.0, sleeps=[])

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(proof_auth, "time", SimpleNamespace(
        monotonic=lambda: clock.now, sleep=sleep,
    ))
    opener = Mock(side_effect=AssertionError("unexpected network request"))
    monkeypatch.setattr(proof_auth.urllib.request, "urlopen", opener)
    return SimpleNamespace(
        clock=clock, opener=opener,
        token=lambda: _json_response({"value": "synthetic-oidc-token"}),
        session=lambda: _json_response({
            "session_token": "synthetic-session", "scope": PRODUCTION_PROOF_SCOPE,
            "release_sha": SHA, "repository": CLAIMS["repository"],
            "workflow_ref": WORKFLOW_REF,
        }),
    )


def _assert_safe_failure(caught, capsys):
    rendered = "".join(traceback.format_exception(caught.value))
    captured = capsys.readouterr()
    assert _PRIVATE not in rendered + captured.out + captured.err
    assert _OIDC_URL not in rendered + captured.out + captured.err
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("statuses", [[], [502], [503], [504], [503, 504]])
def test_oidc_acquisition_retries_only_get_then_exchanges_once(acquisition, statuses):
    errors = [_http_error(status) for status in statuses]
    bodies = [error.fp for error in errors]
    token, session = acquisition.token(), acquisition.session()
    acquisition.opener.side_effect = [*errors, token, session]
    result, retained = proof_auth.acquire_production_proof_session(_FRONTEND)
    assert result == "synthetic-session"
    assert retained["scope"] == PRODUCTION_PROOF_SCOPE
    assert retained["release_sha"] == SHA
    calls = acquisition.opener.call_args_list
    assert [call.args[0].get_method() for call in calls] == ["GET"] * (len(errors) + 1) + ["POST"]
    assert all(call.kwargs["timeout"] == 10 for call in calls[:-1])
    assert calls[-1].kwargs["timeout"] == 45
    assert calls[-1].args[0].full_url == _FRONTEND + "/api/nico/ci-session"
    assert calls[-1].args[0].get_header("Authorization") == "Bearer synthetic-oidc-token"
    assert all(call.args[0] is calls[0].args[0] for call in calls[:-1])
    query = proof_auth.urllib.parse.parse_qs(proof_auth.urllib.parse.urlsplit(calls[0].args[0].full_url).query)
    assert query["audience"] == [proof_auth.DEFAULT_AUDIENCE]
    assert acquisition.clock.sleeps == list(range(1, len(errors) + 1))
    assert all(body.closed for body in bodies)
    assert token.closed and session.closed


def test_oidc_temporary_failure_exhaustion_is_safe(acquisition, capsys):
    errors = [_http_error(503) for _ in range(3)]
    bodies = [error.fp for error in errors]
    acquisition.opener.side_effect = errors
    with pytest.raises(RuntimeError, match="temporary_failure_exhausted") as caught:
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 3
    assert all(call.args[0].get_method() == "GET" for call in acquisition.opener.call_args_list)
    assert acquisition.clock.sleeps == [1, 2]
    assert all(body.closed for body in bodies)
    _assert_safe_failure(caught, capsys)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
def test_oidc_permanent_http_errors_are_not_retried(acquisition, capsys, status):
    error = _http_error(status)
    body = error.fp
    acquisition.opener.side_effect = error
    with pytest.raises(RuntimeError, match="get_http_failure") as caught:
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1
    assert acquisition.clock.sleeps == []
    assert body.closed
    _assert_safe_failure(caught, capsys)


@pytest.mark.parametrize("error", [
    urllib.error.URLError(_PRIVATE),
    urllib.error.URLError(ssl.SSLCertVerificationError(_PRIVATE)),
    ssl.SSLCertVerificationError(_PRIVATE), TimeoutError(_PRIVATE),
])
def test_oidc_transport_errors_are_not_retried(acquisition, capsys, error):
    acquisition.opener.side_effect = error
    with pytest.raises(RuntimeError, match="get_transport_failure") as caught:
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1
    assert acquisition.clock.sleeps == []
    _assert_safe_failure(caught, capsys)


@pytest.mark.parametrize("body,code", [
    (b'{"value":' + _PRIVATE.encode(), "response_invalid"),
    (b'\xff' + _PRIVATE.encode(), "response_invalid"),
    (b'[]', "response_invalid"), (b'{}', "token_unavailable"),
    (b'{"value": null}', "token_unavailable"),
    (b'{"value": "  "}', "token_unavailable"),
    (b'{"value": 123}', "token_unavailable"),
    (b'{"value": {}}', "token_unavailable"),
])
def test_oidc_invalid_response_never_retries_or_exchanges(acquisition, capsys, body, code):
    response = io.BytesIO(body)
    acquisition.opener.side_effect = [response]
    with pytest.raises(ValueError, match=code) as caught:
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1
    assert acquisition.clock.sleeps == []
    assert response.closed
    _assert_safe_failure(caught, capsys)


def test_oidc_body_transport_failure_is_not_retried(acquisition, capsys):
    response = acquisition.token()
    response.read = Mock(side_effect=urllib.error.URLError(_PRIVATE))
    acquisition.opener.side_effect = [response]
    with pytest.raises(RuntimeError, match="get_transport_failure") as caught:
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1
    assert response.closed
    _assert_safe_failure(caught, capsys)


def test_oidc_retry_uses_remaining_budget_as_socket_timeout(acquisition):
    def open_response(request, timeout):
        if acquisition.opener.call_count == 1:
            acquisition.clock.now = 24
            raise _http_error(503)
        return acquisition.token() if request.get_method() == "GET" else acquisition.session()

    acquisition.opener.side_effect = open_response
    proof_auth.acquire_production_proof_session(_FRONTEND)
    assert [call.kwargs["timeout"] for call in acquisition.opener.call_args_list] == [10, 5, 45]
    assert acquisition.clock.sleeps == [1]


@pytest.mark.parametrize("elapsed", [29, 30, 35])
def test_oidc_deadline_prevents_retry_without_backoff_budget(acquisition, elapsed):
    def fail(request, timeout):
        acquisition.clock.now = elapsed
        raise _http_error(503)

    acquisition.opener.side_effect = fail
    with pytest.raises(RuntimeError, match="deadline_exceeded"):
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1
    assert acquisition.clock.sleeps == []


def test_oidc_deadline_is_rechecked_after_sleep(acquisition, monkeypatch):
    acquisition.opener.side_effect = [_http_error(503)]
    monkeypatch.setattr(proof_auth.time, "sleep", lambda _: setattr(acquisition.clock, "now", 30))
    with pytest.raises(RuntimeError, match="deadline_exceeded"):
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1


@pytest.mark.parametrize("elapsed", [30, 35])
def test_oidc_late_response_is_closed_and_not_exchanged(acquisition, elapsed):
    response = acquisition.token()
    original_read = response.read

    def read():
        acquisition.clock.now = elapsed
        return original_read()

    response.read = read
    acquisition.opener.side_effect = [response]
    with pytest.raises(RuntimeError, match="deadline_exceeded"):
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 1
    assert response.closed


def test_session_post_temporary_error_is_never_retried(acquisition):
    error = _http_error(503)
    acquisition.opener.side_effect = [_http_error(503), acquisition.token(), error]
    with pytest.raises(urllib.error.HTTPError) as caught:
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert caught.value is error
    assert [call.args[0].get_method() for call in acquisition.opener.call_args_list] == ["GET", "GET", "POST"]
    assert acquisition.clock.sleeps == [1]
    error.close()


@pytest.mark.parametrize("field,value", [("scope", "operator"), ("release_sha", "b" * 40), ("session_token", "")])
def test_retry_does_not_relax_exchange_validation(acquisition, field, value):
    payload = {"session_token": "synthetic-session", "scope": PRODUCTION_PROOF_SCOPE, "release_sha": SHA}
    acquisition.opener.side_effect = [_http_error(503), acquisition.token(), _json_response({**payload, field: value})]
    with pytest.raises(ValueError, match="session_exchange_invalid"):
        proof_auth.acquire_production_proof_session(_FRONTEND)
    assert acquisition.opener.call_count == 3


@pytest.mark.parametrize("origin", ["http://frontend.invalid", "https://user:pass@frontend.invalid", "https://frontend.invalid/path", "https://frontend.invalid?query=1"])
def test_invalid_origin_fails_before_oidc_get(acquisition, origin):
    with pytest.raises(ValueError, match="frontend_origin_invalid"):
        proof_auth.acquire_production_proof_session(origin)
    acquisition.opener.assert_not_called()


@pytest.mark.parametrize("outcome", ["success", "oidc_exhausted", "post_failed"])
def test_spanish_entrypoint_does_not_duplicate_downstream_proof(acquisition, monkeypatch, outcome):
    # Execute the actual wrapper with a synthetic proof boundary: no browser,
    # assessment, or external network is used. Authentication must finish first.
    intake_boundary = Mock(return_value=0)
    proof = SimpleNamespace(
        install_spanish_terminal_boundary=Mock(), httpx=SimpleNamespace(Client=Mock()),
        base=SimpleNamespace(run_proof=Mock()), _fetch_canonical_json=Mock(),
        telemetry=SimpleNamespace(main=intake_boundary),
    )
    monkeypatch.setitem(sys.modules, "spanish_comprehensive_live_acceptance_v3", proof)
    monkeypatch.setitem(sys.modules, "production_proof_observer_v1", SimpleNamespace(ProofObserver=Mock()))
    path = Path(__file__).resolve().parents[1] / "scripts/spanish_comprehensive_authenticated_live_acceptance_v1.py"
    spec = importlib.util.spec_from_file_location("synthetic_spanish_wrapper", path)
    wrapper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wrapper)
    errors = [_http_error(503) for _ in range(3)]
    acquisition.opener.side_effect = {
        "success": [errors[0], acquisition.token(), acquisition.session()],
        "oidc_exhausted": errors,
        "post_failed": [errors[0], acquisition.token(), errors[1]],
    }[outcome]
    try:
        if outcome == "success":
            assert wrapper.main(["--frontend-url", _FRONTEND]) == 0
        else:
            with pytest.raises((RuntimeError, urllib.error.HTTPError)):
                wrapper.main(["--frontend-url", _FRONTEND])
        assert intake_boundary.call_count == (1 if outcome == "success" else 0)
        methods = [call.args[0].get_method() for call in acquisition.opener.call_args_list]
        assert methods.count("POST") == (0 if outcome == "oidc_exhausted" else 1)
    finally:
        for error in errors:
            error.close()
