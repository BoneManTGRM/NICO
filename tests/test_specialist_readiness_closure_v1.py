from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico import specialist_access_v1 as access


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv('NICO_COMPREHENSIVE_OPERATOR_PASSWORD', 'closure-test-specialist-password')
    monkeypatch.setenv('NICO_OPERATOR_SESSION_SIGNING_SECRET', 'closure-test-independent-signing-secret-at-least-32-bytes')
    monkeypatch.setenv('NICO_ADMIN_TOKEN', 'closure-test-different-administrator')
    monkeypatch.delenv('NICO_SARA_OPERATOR_PASSWORD', raising=False)


def test_report_boundary_blocks_anonymous_and_proof_but_allows_specialist(credentials):
    app = FastAPI()
    for route in ('/reports', '/reports/client-report', '/reports/client-report/download'):
        app.add_api_route(route, lambda: {'status': 'test_fixture'}, methods=['GET', 'POST'])
    app.add_api_route('/health', lambda: {'status': 'ok'}, methods=['GET'])
    installed = access.install_specialist_access(app)
    assert installed['all_report_routes_protected'] is True
    client = TestClient(app)
    specialist, _ = access.issue_specialist_session({'authority': 'nico_comprehensive_operator'})
    proof, _ = access.issue_specialist_session({'authority': 'github_actions_production_proof'},
                                             scope=access.PRODUCTION_PROOF_SCOPE, retained_claims={
                                                 "repository": "BoneManTGRM/NICO", "ref": "refs/heads/main",
                                                 "sha": "a" * 40, "workflow_ref": "test-only",
                                                 "run_id": "123", "run_attempt": "1"})
    for method in (client.get, client.post):
        for route in ('/reports', '/reports/client-report', '/reports/client-report/download'):
            assert method(route).status_code == 401
            assert method(route, headers={'X-NICO-Operator-Session': proof}).status_code == 403
            response = method(route, headers={'X-NICO-Operator-Session': specialist})
            assert response.status_code == 200
            assert 'no-store' in response.headers['cache-control']
    assert client.get('/health').status_code == 200
    assert not access._protected_request(access.SESSION_ROUTE)
    assert not access._protected_request(access.GITHUB_ACTIONS_SESSION_ROUTE)


def _bootstrap_assertions(code: str) -> None:
    # Importing the final bootstrap binds process-global application routes. Use a
    # fresh interpreter so these integration checks cannot mutate unrelated tests.
    import subprocess
    import sys
    from pathlib import Path

    prelude = "from nico.api import specialist_ship_ready_bootstrap as bootstrap\nfrom nico import specialist_access_v1 as access\n"
    result = subprocess.run([sys.executable, "-c", prelude + code],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_positive_self_test_uses_current_scope_and_exposes_no_secrets(credentials):
    _bootstrap_assertions("""
result = bootstrap._positive_authentication_self_test(bootstrap._configured_credentials())
assert result == {'operator_credential_self_test': True, 'session_round_trip_self_test': True,
                  'positive_authentication_verified_server_side': True}
assert all(isinstance(value, bool) for value in result.values())
assert 'closure-test' not in str(result)
""")


@pytest.mark.parametrize('fault', ['missing_operator', 'bad_signature', 'wrong_scope', 'wrong_authority', 'exception'])
def test_positive_self_test_never_clears_a_broken_boundary(credentials, fault):
    _bootstrap_assertions("fault = " + repr(fault) + "\n" + """
import os
if fault == 'missing_operator':
    os.environ.pop('NICO_COMPREHENSIVE_OPERATOR_PASSWORD')
elif fault == 'bad_signature':
    os.environ['NICO_OPERATOR_SESSION_SIGNING_SECRET'] = 'short'
elif fault == 'wrong_scope':
    bootstrap.validate_specialist_session = lambda *a, **k: {'scope': access.PRODUCTION_PROOF_SCOPE, 'authority': 'nico_comprehensive_operator'}
elif fault == 'wrong_authority':
    bootstrap.require_comprehensive_operator = lambda supplied: (True, {'authority': 'nico_admin'})
else:
    def broken(*args, **kwargs):
        raise RuntimeError('closure-test-secret-must-not-be-exposed')
    bootstrap.issue_specialist_session = broken
result = bootstrap._positive_authentication_self_test(bootstrap._configured_credentials())
assert result['positive_authentication_verified_server_side'] is False
assert 'closure-test' not in str(result)
""")


def test_readiness_requires_self_test_both_route_boundaries_and_rate_limits(credentials):
    _bootstrap_assertions("""
installed = {'installed': True, 'session_signing_configured': True, 'all_assessment_routes_protected': True,
             'all_report_routes_protected': True, 'rate_limiting': True}
bootstrap.SPECIALIST_ACCESS = installed
bootstrap.REVIEW_SESSION_BRIDGE = {'installed': True}
bootstrap.APPROVED_LIFECYCLE_CONSISTENCY = {'installed': True, 'cross_format_fail_closed': True}
bootstrap.comprehensive_release_provenance = lambda: {'deployment_identity_established': True, 'frontend_identity_established': True}
bootstrap.app.state.nico_comprehensive_production_runtime = {
    'status': 'ready', 'survives_container_replacement_verified': True,
    'human_review_required': True, 'client_delivery_allowed': False}
assert bootstrap.specialist_readiness()['status'] == 'ready'
for key in ('all_assessment_routes_protected', 'all_report_routes_protected', 'rate_limiting'):
    installed[key] = False
    assert bootstrap.specialist_readiness()['status'] == 'blocked'
    installed[key] = True
bootstrap._positive_authentication_self_test = lambda _: {
    'operator_credential_self_test': False, 'session_round_trip_self_test': False,
    'positive_authentication_verified_server_side': False}
result = bootstrap.specialist_readiness()
assert result['status'] == 'blocked'
assert result['human_review_required'] is True
assert result['client_delivery_allowed'] is False
assert result['secrets_exposed'] is False
""")
