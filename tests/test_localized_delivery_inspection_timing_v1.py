"""Real same-run exports retain exact outputs while avoiding irrelevant inspection."""
from copy import deepcopy
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_comprehensive_localized_export_v1 import source_status
from nico import comprehensive_same_run_locale_report_v1 as locale
from nico import comprehensive_commercial_ship_projection_v3 as commercial
from nico.comprehensive_localized_export_v1 import localized_evidence_package


def _spanish_source():
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    reports = rebuild_client_artifacts(_package('es-MX'))
    canonical = reports['json']
    reports['report_id'] = canonical.get('report_id') or 'report_spanish_timing_fixture'
    reports['canonical_truth_sha256'] = locale.canonical_sha256(canonical)
    return {**{key: canonical['identity'][key] for key in
               ('run_id', 'repository', 'commit_sha', 'evidence_ledger_id')},
            'report_language': 'es-MX', 'terminal': True, 'reports': reports}


def pending(source):
    result = deepcopy(source)
    result.update(human_review_required=True, human_review_completed=False,
                  approval_status='pending_human_approval', client_delivery_allowed=False)
    return result


@pytest.mark.parametrize('kind', ['markdown', 'zip'])
def test_cross_language_skips_only_presentation_inspection_with_identical_output(source_status, monkeypatch, kind):
    source = pending(_spanish_source())
    before = deepcopy(source)
    build = locale.build_same_run_locale_markdown_projection if kind == 'markdown' else localized_evidence_package
    # A true presentation finding only forces regeneration, already required by the English target.
    inspections = []
    def force_reprojection(*args):
        inspections.append(True)
        return True
    with monkeypatch.context() as previous_path:
        previous_path.setattr(commercial, '_cross_language_regeneration_required', lambda *args: False)
        previous_path.setattr(commercial, '_source_pdf_requires_integrity_reprojection', force_reprojection)
        expected = build(source, 'en')
    assert inspections, 'expected output must exercise the pre-change inspection path'
    def forbidden(*args):
        raise AssertionError('cross-language regeneration must not inspect source PDF presentation')
    monkeypatch.setattr(commercial, '_source_pdf_requires_integrity_reprojection', forbidden)
    actual = build(source, 'en')
    if kind == 'markdown':
        assert actual == expected  # Includes bytes/hash, canonical truth and both lifecycles.
        assert actual['canonical_truth_preserved'] is True
        assert actual['report']['client_delivery_allowed'] is False
    else:
        assert actual.body == expected.body  # Every ZIP member/hash is unchanged.
        assert dict(actual.headers) == dict(expected.headers)
        assert actual.headers['x-nico-client-delivery-allowed'] == 'false'
    assert source == before


@pytest.mark.parametrize('kind', ['markdown', 'zip'])
def test_same_language_still_checks_source_presentation(source_status, monkeypatch, kind):
    def inspected(*args):
        raise RuntimeError('same-language presentation check reached')
    monkeypatch.setattr(commercial, '_source_pdf_requires_integrity_reprojection', inspected)
    build = locale.build_same_run_locale_markdown_projection if kind == 'markdown' else localized_evidence_package
    with pytest.raises(RuntimeError, match='same-language presentation check reached'):
        build(pending(source_status), 'en')


@pytest.mark.parametrize('kind,damage', [('markdown', 'truth'), ('markdown', 'identity'),
                                       ('markdown', 'language'), ('zip', 'truth'), ('zip', 'identity'), ('zip', 'language'), ('zip', 'html')])
def test_cross_language_still_rejects_tampered_inputs(source_status, kind, damage):
    source = pending(_spanish_source())
    if damage == 'truth': source['reports']['canonical_truth_sha256'] = '0' * 64
    elif damage == 'identity': source['commit_sha'] = 'f' * 40
    elif damage == 'language': source['report_language'] = 'en'
    else: source['reports']['html'] += 'tampered'
    build = locale.build_same_run_locale_markdown_projection if kind == 'markdown' else localized_evidence_package
    with pytest.raises(ValueError):
        build(source, 'en')


@pytest.mark.parametrize('kind', ['markdown', 'zip'])
def test_real_routes_emit_bounded_phase_timings_without_contents(source_status, caplog, kind):
    source = pending(_spanish_source())
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(status_artifact_read_only=lambda _: source)
    locale.install_same_run_locale_report(app)
    path = locale.ROUTE if kind == 'markdown' else locale.EVIDENCE_PACKAGE_ROUTE
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    response = TestClient(app).get(path.format(run_id=source['run_id'], report_language='en'))
    assert response.status_code == 200, response.text[:200]
    records = [json.loads(r.getMessage().split('=', 1)[1]) for r in caplog.records
               if r.getMessage().startswith('NICO_REPORT_TIMING=')]
    assert len(records) == 1
    row = records[0]
    assert row['outcome'] == 'completed'
    assert row['http_transfer_completion_inferred'] is False
    required = {'controller_status', 'artifact_preparation', 'truth_parity_projection'}
    required |= {'markdown_render'} if kind == 'markdown' else {'artifact_render', 'artifact_finalize', 'zip_encoding'}
    assert required <= row['phases'].keys()
    for value in row['phases'].values():
        assert set(value) == {'calls', 'elapsed_ms', 'thread_cpu_ms'}
        assert value['calls'] > 0 and value['elapsed_ms'] >= 0
    assert source['repository'] not in json.dumps(row)
    assert source['commit_sha'] not in json.dumps(row)


@pytest.mark.parametrize('kind', ['markdown', 'zip'])
def test_route_failure_timing_does_not_leak_exception_payload(caplog, kind):
    app = FastAPI()
    def failure(_): raise ValueError('PRIVATE_REPORT_AND_CREDENTIAL_SENTINEL')
    app.state.comprehensive_api_controller = SimpleNamespace(status_artifact_read_only=failure)
    locale.install_same_run_locale_report(app)
    path = locale.ROUTE if kind == 'markdown' else locale.EVIDENCE_PACKAGE_ROUTE
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    response = TestClient(app).get(path.format(run_id='comprun_' + 'a'*32, report_language='en'))
    assert response.status_code == 409
    rows = [json.loads(r.getMessage().split('=',1)[1]) for r in caplog.records
            if r.getMessage().startswith('NICO_REPORT_TIMING=')]
    assert len(rows) == 1 and rows[0]['outcome'] == 'failed'
    assert rows[0]['error_type'] == 'ValueError'
    assert 'PRIVATE_REPORT_AND_CREDENTIAL_SENTINEL' not in json.dumps(rows)
