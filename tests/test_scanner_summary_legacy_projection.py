import json
import sqlite3
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import _browser_projection_sha256
from tests.test_comprehensive_run_service import _store, _executors, _run_to_review
from tests.test_scanner_completion_gate import good
from tests.test_comprehensive_mobile_recovery_v1 import _record as report_fixture

RUN = 'comprun_legacy_scanner_summary_test'
SHA = 'a' * 40
HEADERS = {'x-nico-browser-projection': 'terminal-manifest-v1'}


def app_for(store, executors=None):
    service = ComprehensiveRunService(store, executors or {})
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=ComprehensiveApiController(service))
    return app, service


def legacy_run(tmp_path, *, partial=False, stale_summary=False):
    database = tmp_path / 'legacy.sqlite3'
    store = _store(database)
    executors = _executors()
    original = executors['final_report_generation']

    def final(context):
        output = original(context)
        final_fixture = report_fixture()['stage_results']['final_comprehensive_report_generation']
        report = final_fixture['report_package']
        output['report_package'] = report
        output['assessment'] = final_fixture['assessment']
        report['json']['identity'].update({key: context[key] for key in (
            'run_id', 'repository', 'commit_sha', 'evidence_ledger_id')})
        records = good()['requested_scanner_records']
        for record in records:
            record.update(run_id=RUN, commit_sha=SHA)
            if partial and record['scanner_name'] in {'npm-audit', 'typescript'}:
                record.update(state='unavailable', completed=False, verified=False,
                              raw_artifact_retention_complete=False, raw_artifact_sha256='')
        report['json']['requested_scanner_records'] = records
        report['json']['repository_evidence'] = {'file_evidence': {'sampled_paths': ['package.json', 'src/index.ts']}}
        report['canonical_truth_sha256'] = canonical_sha256(report['json'])
        return output

    executors['final_report_generation'] = final
    app, service = app_for(store, executors)
    service.start(run_id=RUN, repository='BoneManTGRM/NICO', commit_sha=SHA,
                  evidence_ledger_id='ledger_legacy_summary', customer_id='test_customer',
                  project_id='test_project', authorized=True)
    _run_to_review(service, RUN)
    before = store.load(RUN)
    projection = store.load_browser_projection(RUN)
    assert projection['response_projection']['artifact_integrity_valid'] is True
    assert projection['scanner_execution_summary']['status'] == ('partial' if partial else 'complete')
    if stale_summary:
        projection['scanner_execution_summary'].pop('evaluation_policy', None)
        projection['scanner_execution_summary']['percent'] = 88
    else:
        projection.pop('scanner_execution_summary', None)
    # Model a previously valid saved projection produced before the new field.
    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE nico_comprehensive_browser_projections SET projection=?, projection_sha256=? WHERE run_id=?',
            (json.dumps(projection), _browser_projection_sha256(projection), RUN))
        connection.commit()
    return database, store, app, before


@pytest.mark.parametrize('partial, status, percent', [(False, 'complete', 100), (True, 'partial', 78)])
def test_legacy_terminal_projection_refreshes_once_without_changing_run(tmp_path, monkeypatch, partial, status, percent):
    database, store, app, before = legacy_run(tmp_path, partial=partial)
    loads = []
    original_load = store.load

    def counted(run_id):
        loads.append(run_id)
        return original_load(run_id)

    monkeypatch.setattr(store, 'load', counted)
    response = TestClient(app).get(f'/assessment/comprehensive-run/{RUN}', headers=HEADERS)
    assert response.status_code == 200
    summary = response.json()['scanner_execution_summary']
    assert summary['status'] == status
    assert summary['percent'] == percent
    assert summary['run_id'] == RUN and summary['commit_sha'] == SHA
    assert response.json()['human_review_completed'] is False
    assert response.json()['client_delivery_allowed'] is False
    assert loads == [RUN]
    assert original_load(RUN) == before

    restarted_store = _store(database)
    restarted_app, _ = app_for(restarted_store)

    def forbidden_load(_):
        raise AssertionError('refreshed summary must survive restart without a full record read')

    monkeypatch.setattr(restarted_store, 'load', forbidden_load)
    result = TestClient(restarted_app).get(f'/assessment/comprehensive-run/{RUN}', headers=HEADERS)
    assert result.status_code == 200
    assert result.json()['scanner_execution_summary'] == summary


def test_corrupted_legacy_projection_is_not_repaired_into_authority(tmp_path):
    database, store, app, before = legacy_run(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE nico_comprehensive_browser_projections SET projection_sha256=? WHERE run_id=?', ('0'*64, RUN))
        connection.commit()
    result = TestClient(app).get(f'/assessment/comprehensive-run/{RUN}', headers=HEADERS)
    assert result.status_code == 503
    assert result.json()['detail']['code'] == 'comprehensive_browser_projection_integrity_invalid'
    assert store.load(RUN) == before


def test_old_policy_projection_is_refreshed_without_rewriting_history(tmp_path):
    _, store, app, before = legacy_run(tmp_path, partial=True, stale_summary=True)
    response = TestClient(app).get(f'/assessment/comprehensive-run/{RUN}', headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['scanner_execution_summary']['percent'] == 78
    assert response.json()['scanner_execution_summary']['evaluation_policy'] == 'node-input-inventory-v1'
    assert store.load(RUN) == before


def test_refresh_cannot_overwrite_a_concurrent_new_revision(tmp_path):
    from nico.comprehensive_run_record import _record_hash

    database, store, app, before = legacy_run(tmp_path)
    original_builder = store._browser_projection_builder

    def racing_builder(record):
        stale = original_builder(record)
        store.bind_browser_projection_builder(original_builder)
        newer = deepcopy(record)
        newer['revision'] += 1
        newer['integrity_sha256'] = _record_hash(newer)
        store.save(newer, expected_revision=record['revision'])
        # Distinguish the losing response from the valid newer projection.
        stale['scanner_execution_summary']['percent'] = 1
        return stale

    store.bind_browser_projection_builder(racing_builder)
    response = TestClient(app).get(f'/assessment/comprehensive-run/{RUN}', headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['revision'] == before['revision'] + 1
    assert response.json()['scanner_execution_summary']['percent'] == 100
    assert store.load_browser_projection(RUN)['revision'] == before['revision'] + 1
