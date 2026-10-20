"""Release admission checks; historical artifacts retain their original validators."""
import pytest
from nico import comprehensive_same_run_locale_report_v1 as locale
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.ordinary_report_language_release_v1 import require_new_report_language
from test_frozen_source_pdf_readonly_work_v1 import _status


@pytest.mark.parametrize('language', ['es', 'es-MX', 'ES_mx', 'es-ES'])
def test_new_spanish_intake_rejected_before_service_work(language):
    controller = object.__new__(ComprehensiveApiController)
    for _ in range(2):
        with pytest.raises(ValueError, match='spanish_report_generation_unavailable'):
            controller.start({'report_language': language})


@pytest.mark.parametrize('language', [None, 'en', 'en-US'])
def test_english_language_admitted(language):
    require_new_report_language(language)


@pytest.mark.parametrize('builder', [locale.build_same_run_locale_pdf_response,
    locale.build_same_run_locale_report, locale.build_same_run_locale_markdown_projection])
def test_new_spanish_projection_rejected_without_rendering(monkeypatch, builder):
    status, _ = _status('en')
    def forbidden(*args, **kwargs):
        pytest.fail('Spanish generation must not render or clone canonical content')
    monkeypatch.setattr(locale, '_render_target', forbidden)
    monkeypatch.setattr(locale, 'deepcopy', forbidden)
    for _ in range(2):
        with pytest.raises(ValueError, match='spanish_report_generation_unavailable'):
            builder(status, 'es-MX')


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_frozen_pdf_retains_bytes_and_integrity_checks(monkeypatch, language):
    status, expected = _status(language)
    def forbidden(*args, **kwargs):
        pytest.fail('Frozen artifact must not regenerate')
    monkeypatch.setattr(locale, '_render_target', forbidden)
    for _ in range(2):
        response = locale.build_same_run_locale_pdf_response(status, language)
        assert response.body == expected
        assert response.headers['x-nico-client-delivery-allowed'] == 'false'
    status['reports']['json']['assessment']['technical_score'] = 91
    with pytest.raises(ValueError, match='canonical_truth_hash_mismatch'):
        locale.build_same_run_locale_pdf_response(status, language)


def test_frozen_spanish_without_pdf_cannot_regenerate():
    status, _ = _status('es-MX')
    del status['reports']['pdf_base64']
    with pytest.raises(ValueError, match='spanish_report_generation_unavailable'):
        locale.build_same_run_locale_report(status, 'es-MX')


def test_public_intake_rejects_before_reservation(monkeypatch):
    from nico import comprehensive_api_routes as routes
    monkeypatch.setattr(routes, '_prepare_public_intake_reservation_payload', lambda payload: payload)
    def forbidden(*args, **kwargs):
        pytest.fail('Unavailable language must not reserve or execute a run')
    monkeypatch.setattr(routes, '_reserve_prepared_public_intake', forbidden)
    for _ in range(2):
        with pytest.raises(ValueError, match='spanish_report_generation_unavailable'):
            routes._intake(None, {'report_language': 'es-MX'})


@pytest.mark.parametrize('suffix', ['', '/pdf', '/evidence-package'])
def test_http_projection_returns_prompt_language_block(suffix):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    status, _ = _status('en')
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(status_read_only=lambda run_id: status)
    locale.install_same_run_locale_report(app)
    path = locale.ROUTE.format(run_id=status['run_id'], report_language='es-MX') + suffix
    response = TestClient(app).get(path)
    assert response.status_code == 409
    assert response.json()['detail']['reason'] == 'spanish_report_generation_unavailable'


def test_public_intake_language_rejection_is_structured_and_nonretryable():
    from nico.comprehensive_api_routes import _translate_error
    error = _translate_error(ValueError('spanish_report_generation_unavailable'))
    assert error.status_code == 422
    assert error.detail['code'] == 'spanish_report_generation_unavailable'
    assert error.detail['retryable'] is False
    assert error.detail['human_review_required'] is True
    assert error.detail['client_delivery_allowed'] is False


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_intake_record_and_stage_keep_requested_locale_without_english_fallback(language):
    from nico.comprehensive_api_routes import _prepare_public_intake_reservation_payload
    from nico.comprehensive_run_record import create_comprehensive_run_record, apply_comprehensive_stage_result
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    payload = _prepare_public_intake_reservation_payload({
        'run_id': 'comprun_' + 'a' * 32, 'repository': 'owner/repo',
        'authorized': True, 'authorization_confirmed': True, 'report_language': language,
    })
    assert payload['report_language'] == language
    record = create_comprehensive_run_record(
        run_id=payload['run_id'], repository=payload['repository'], commit_sha='b' * 40,
        evidence_ledger_id='ledger_locale', customer_id=payload['customer_id'],
        project_id=payload['project_id'], authorized=True, report_language=payload['report_language'],
    )
    assert record['identity']['report_language'] == language
    updated = apply_comprehensive_stage_result(record, stage_id=COMPREHENSIVE_STAGES[0],
                                               result={'status': 'complete'})
    assert updated['stage_results'][COMPREHENSIVE_STAGES[0]]['report_language'] == language
    assert updated['human_review_required'] is True
    assert updated['client_delivery_allowed'] is False


@pytest.mark.parametrize('language', ['es', 'es-MX', 'ES_mx', 'en', 'en-US'])
def test_real_public_intake_preparation_and_language_gate_precede_reservation(monkeypatch, language):
    from nico import comprehensive_api_routes as routes
    from nico import ordinary_report_language_release_v1 as release
    events = []
    original_prepare = routes._prepare_public_intake_reservation_payload
    original_gate = release.require_new_report_language

    def prepare(payload):
        events.append('prepare')
        return original_prepare(payload)

    def gate(value):
        events.append(('gate', value))
        return original_gate(value)

    def reserve(request, prepared):
        events.append(('reserve', prepared['report_language']))
        return {'lease_owner': True}

    def execute(request, reservation):
        events.append('execute_double')
        return {'isolated_test_only': True}

    monkeypatch.setattr(routes, '_prepare_public_intake_reservation_payload', prepare)
    monkeypatch.setattr(release, 'require_new_report_language', gate)
    monkeypatch.setattr(routes, '_reserve_prepared_public_intake', reserve)
    monkeypatch.setattr(routes, '_execute_public_intake_reservation', execute)
    payload = {'repository': 'owner/fixture', 'run_id': 'comprun_' + 'c' * 32,
               'authorized': True, 'authorization_confirmed': True, 'report_language': language}
    if language.lower().startswith('es'):
        with pytest.raises(ValueError, match='^spanish_report_generation_unavailable$'):
            routes._intake(None, payload)
        assert events == ['prepare', ('gate', language)]
    else:
        assert routes._intake(None, payload) == {'isolated_test_only': True}
        assert events == ['prepare', ('gate', language), ('reserve', language), 'execute_double']
    events.clear()
    with pytest.raises(ValueError, match='explicit_authorization_required'):
        routes._intake(None, {**payload, 'authorized': False})
    assert events == ['prepare']
