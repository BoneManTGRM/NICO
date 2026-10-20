"""A rollout rejection must keep its safe reason and pre-acquisition boundary."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from nico import hosted_provider_comprehensive_runtime_v1 as runtime
from nico.provider_rollout_control_v1 import ProviderRolloutRegistry, STATE_KEY


def test_missing_reference_retains_declared_status_before_acquisition(monkeypatch):
    monkeypatch.delenv('NICO_PROVIDER_GITHUB_CREDENTIAL_REFERENCE', raising=False)
    monkeypatch.setenv('NICO_PROVIDER_GITHUB_ENABLED', 'true')
    monkeypatch.setenv('NICO_PROVIDER_GITHUB_ROLLOUT', 'controlled_pilot')
    monkeypatch.setattr(runtime, '_operator_required', lambda token: None)
    calls = []
    monkeypatch.setattr(runtime, 'capture_repository_snapshot', lambda payload: calls.append('capture'))
    monkeypatch.setattr(runtime.api_routes, '_controller', lambda request: calls.append('controller'))
    state = SimpleNamespace()
    setattr(state, STATE_KEY, ProviderRolloutRegistry())
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    with pytest.raises(HTTPException) as caught:
        runtime._operator_intake(request, {
            'provider': 'github', 'repository': 'owner/synthetic-fixture',
            'expected_commit_sha': 'a' * 40, 'authorized': True,
            'authorization_confirmed': True, 'execution_mode': 'internal_test',
        }, 'synthetic-test-admin')
    assert caught.value.status_code == 409
    assert caught.value.detail == {
        'code': 'provider_credential_reference_missing',
        'phase': 'provider_preflight', 'assessment_started': False,
        'retryable': False, 'human_review_required': True,
        'client_delivery_allowed': False,
    }
    assert calls == []


@pytest.mark.parametrize('provider', ['github', 'gitlab'])
@pytest.mark.parametrize('language', ['es', 'es-MX', 'ES_mx'])
def test_spanish_operator_intake_stops_before_preflight_or_capture(monkeypatch, provider, language):
    monkeypatch.setattr(runtime, 'require_admin_write', lambda token: (token == 'synthetic-admin', {}))
    def forbidden(*args, **kwargs):
        pytest.fail('Unavailable language reached acquisition or controller')
    monkeypatch.setattr(ProviderRolloutRegistry, 'preflight', forbidden)
    monkeypatch.setattr(runtime, 'capture_repository_snapshot', forbidden)
    monkeypatch.setattr(runtime, 'capture_hosted_provider_snapshot', forbidden)
    monkeypatch.setattr(runtime.api_routes, '_controller', lambda request: SimpleNamespace(start=forbidden))
    state = SimpleNamespace()
    setattr(state, STATE_KEY, ProviderRolloutRegistry())
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    data = {'provider': provider, 'repository': 'owner/synthetic-fixture',
            'expected_commit_sha': 'a' * 40, 'authorized': True,
            'authorization_confirmed': True, 'report_language': language}
    for _ in range(3):
        with pytest.raises(ValueError, match='^spanish_report_generation_unavailable$') as caught:
            runtime._operator_intake(request, data, 'synthetic-admin')
        translated = runtime.api_routes._translate_error(caught.value)
        assert translated.status_code == 422
        assert translated.detail == {
            'code': 'spanish_report_generation_unavailable',
            'message': 'Spanish generation is unavailable; the requested language was not changed.',
            'retryable': False,
            'human_review_required': True,
            'client_delivery_allowed': False,
        }
    with pytest.raises(HTTPException) as caught:
        runtime._operator_intake(request, data, 'unauthorized')
    assert caught.value.status_code == 403
    with pytest.raises(ValueError, match='explicit_authorization_required'):
        runtime._operator_intake(request, {**data, 'authorized': False}, 'synthetic-admin')
    with pytest.raises(ValueError, match='raw_provider_credentials_prohibited'):
        runtime._operator_intake(request, {**data, 'token': 'synthetic-only'}, 'synthetic-admin')
