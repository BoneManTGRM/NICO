"""Bilingual integration contract, with separately retained red baseline evidence.

Separate from the immutable renderer qualification export. No acquisition,
assessment, HTTP, credentials, or production admission override is performed.
"""
from types import SimpleNamespace

import pytest


ALIASES = [('en', 'en'), ('en-US', 'en'), ('es', 'es-MX'),
           ('es-MX', 'es-MX'), ('ES_mx', 'es-MX')]


@pytest.mark.parametrize('submitted,canonical', ALIASES)
def test_public_admission_preserves_explicit_canonical_locale(monkeypatch, submitted, canonical):
    from nico import comprehensive_api_routes as routes
    observed = []
    run_id = 'comprun_' + 'c' * 32

    def reserve(request, prepared):
        observed.append(prepared)
        return {'lease_owner': True}

    monkeypatch.setattr(routes, '_reserve_prepared_public_intake', reserve)
    monkeypatch.setattr(routes, '_execute_public_intake_reservation',
                        lambda request, reservation: {'run_id': run_id})
    payload = dict(repository='owner/synthetic', run_id=run_id, authorized=True,
                   authorization_confirmed=True, report_language=submitted)
    assert routes._intake(None, payload) == {'run_id': run_id}
    assert len(observed) == 1
    assert observed[0]['report_language'] == canonical
    assert payload['report_language'] == submitted
    observed.clear()
    with pytest.raises(ValueError, match='explicit_authorization_required'):
        routes._intake(None, {**payload, 'authorized': False})
    assert observed == []


@pytest.mark.parametrize('language', ['fr', 'de', 'es-ES', 'en-invalid'])
def test_unsupported_locale_is_rejected_before_reservation(monkeypatch, language):
    from nico import comprehensive_api_routes as routes

    def forbidden(*args, **kwargs):
        pytest.fail('Unsupported language reached reservation')

    monkeypatch.setattr(routes, '_reserve_prepared_public_intake', forbidden)
    with pytest.raises(ValueError, match='^unsupported_report_language$'):
        routes._intake(None, dict(repository='owner/synthetic',
            run_id='comprun_' + 'd' * 32, authorized=True,
            authorization_confirmed=True, report_language=language))


@pytest.mark.parametrize('submitted,canonical', ALIASES)
def test_operator_admission_reaches_unchanged_preflight_with_canonical_locale(
    monkeypatch, submitted, canonical,
):
    from nico import hosted_provider_comprehensive_runtime_v1 as runtime
    from nico.provider_rollout_control_v1 import ProviderRolloutRegistry, STATE_KEY
    from fastapi import HTTPException

    class PreflightReached(Exception):
        pass

    observed = []

    def preflight(self, payload, **kwargs):
        observed.append((payload['locale'], kwargs['operator_authorized']))
        raise PreflightReached

    def forbidden(*args, **kwargs):
        pytest.fail('Synthetic admission test must not acquire a repository')

    monkeypatch.setattr(runtime, 'require_admin_write',
                        lambda token: (token == 'synthetic-admin', {}))
    monkeypatch.setattr(ProviderRolloutRegistry, 'preflight', preflight)
    monkeypatch.setattr(runtime, 'capture_repository_snapshot', forbidden)
    monkeypatch.setattr(runtime, 'capture_hosted_provider_snapshot', forbidden)
    state = SimpleNamespace()
    setattr(state, STATE_KEY, ProviderRolloutRegistry())
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    payload = dict(provider='github', repository='owner/synthetic',
                   expected_commit_sha='a' * 40, authorized=True,
                   authorization_confirmed=True, report_language=submitted)
    with pytest.raises(HTTPException) as caught:
        runtime._operator_intake(request, payload, 'unauthorized')
    assert caught.value.status_code == 403
    assert observed == []
    with pytest.raises(PreflightReached):
        runtime._operator_intake(request, payload, 'synthetic-admin')
    assert observed == [(canonical, True)]
    assert payload['report_language'] == submitted


def test_unsupported_locale_error_is_safe_nonretryable_and_delivery_blocked():
    from nico.comprehensive_api_routes import _translate_error
    error = _translate_error(ValueError('unsupported_report_language'))
    assert error.status_code == 422
    assert isinstance(error.detail, dict)
    assert error.detail['code'] == 'unsupported_report_language'
    assert error.detail['retryable'] is False
    assert error.detail['human_review_required'] is True
    assert error.detail['client_delivery_allowed'] is False


@pytest.mark.parametrize('submitted,canonical', ALIASES)
def test_controller_passes_canonical_language_without_mutating_input(submitted, canonical):
    from copy import deepcopy
    from nico.comprehensive_api_controller import ComprehensiveApiController
    calls = []
    controller = object.__new__(ComprehensiveApiController)
    controller._service = SimpleNamespace(start=lambda **kwargs: calls.append(kwargs) or kwargs)
    controller._response = lambda record, **kwargs: record
    payload = dict(repository='owner/synthetic', commit_sha='a' * 40,
                   run_id='comprun_' + 'e' * 32, evidence_ledger_id='ledger_synthetic',
                   customer_id='synthetic_customer', project_id='synthetic_project',
                   authorized=True, authorization_confirmed=True, report_language=submitted)
    original = deepcopy(payload)
    assert controller.start(payload)['report_language'] == canonical
    assert payload == original
    assert len(calls) == 1
    calls.clear()
    with pytest.raises(ValueError, match='explicit_authorization_required'):
        controller.start({**payload, 'authorized': False})
    with pytest.raises(ValueError, match='unsupported_report_language'):
        controller.start({**payload, 'report_language': 'fr'})
    assert calls == []


@pytest.mark.parametrize('alias,canonical', ALIASES)
def test_public_alias_has_same_new_reservation_fingerprint(alias, canonical):
    from nico.comprehensive_api_routes import _prepare_public_intake_reservation_payload
    from nico.comprehensive_run_store import _public_intake_payload_sha256
    payload = dict(repository='owner/synthetic', run_id='comprun_' + 'f' * 32,
                   authorized=True, authorization_confirmed=True)
    a = _prepare_public_intake_reservation_payload({**payload, 'report_language': alias})
    b = _prepare_public_intake_reservation_payload({**payload, 'report_language': canonical})
    assert a == b
    assert _public_intake_payload_sha256(a) == _public_intake_payload_sha256(b)


@pytest.mark.parametrize('invalid', ['', ' ', False, 0, [], {}, 'es-invalid', 'en-GB'])
def test_language_validation_never_silently_falls_back(invalid):
    from nico.ordinary_report_language_release_v1 import normalize_new_report_language
    with pytest.raises(ValueError, match='^unsupported_report_language$'):
        normalize_new_report_language(invalid)


@pytest.mark.parametrize('builder_name', [
    'build_same_run_locale_report', 'build_same_run_locale_pdf_response',
    'build_same_run_locale_markdown_projection',
])
def test_nonterminal_spanish_projection_keeps_normal_readiness_rejection(builder_name):
    from nico import comprehensive_same_run_locale_report_v1 as locale
    with pytest.raises(ValueError, match='^terminal_report_required$'):
        getattr(locale, builder_name)({'terminal': False}, 'es-MX')
