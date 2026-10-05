from __future__ import annotations

import base64
import hashlib
import io
import json
import sqlite3

import pytest
from fastapi import FastAPI, HTTPException
from reportlab.pdfgen import canvas

from nico import comprehensive_run_store as store_module
from nico import comprehensive_same_run_locale_report_v1 as locale
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import _record_hash, create_comprehensive_run_record
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_storage_codec_v1 import decode_run_storage, encode_run_storage
from nico.comprehensive_run_store import ComprehensiveRunStore


@pytest.fixture
def retained(tmp_path, monkeypatch):
    identity = dict(run_id='comprun_' + 'd' * 32, repository='owned/cache-control',
                    commit_sha='b' * 40, evidence_ledger_id='ledger_cache_control',
                    customer_id='owned_customer', project_id='owned_project', report_language='en')
    record = create_comprehensive_run_record(**identity, authorized=True)
    canonical = dict(report_id='report_cache_control', report_language='en', locale='en',
                     identity=identity, assessment=dict(report_language='en', locale='en',
                     technical_score=92, human_review_required=True, client_delivery_allowed=False),
                     stage_summaries=[], human_review_required=True, client_delivery_allowed=False,
                     owned_evidence='owned diagnostic ñ ' * 500_000)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, invariant=1)
    pdf.drawString(40, 750, 'Owned retained PDF cache control')
    pdf.save()
    body = output.getvalue()
    package = dict(report_id=canonical['report_id'], report_language='en', locale='en', json=canonical,
                   canonical_truth_sha256=canonical_sha256(canonical), markdown='# Owned report',
                   html='<p>Owned report</p>', pdf_base64=base64.b64encode(body).decode(),
                   pdf_sha256=hashlib.sha256(body).hexdigest(), human_review_required=True,
                   client_delivery_allowed=False)
    record.update(status='review_required', terminal=True, current_stage='client_acceptance_pending',
                  completed_stages=list(COMPREHENSIVE_STAGES), progress_percent=100.0,
                  stage_results={'final_comprehensive_report_generation': dict(
                      status='complete', report_package=package, assessment=canonical['assessment'])})
    record['integrity_sha256'] = _record_hash(record)
    database = tmp_path / 'retained.sqlite3'
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    store.ensure_schema()
    store.create(record)
    controller = ComprehensiveApiController(ComprehensiveRunService(store, {}))
    app = FastAPI()
    app.state.comprehensive_api_controller = controller
    locale.install_same_run_locale_report(app)
    endpoint = next(route.endpoint for route in app.routes if getattr(route, 'path', '') == locale.PDF_ROUTE)
    calls = []
    original = store_module._decode_run_payload

    def observe(payload):
        calls.append(True)
        return original(payload)

    monkeypatch.setattr(store_module, '_decode_run_payload', observe)
    return database, identity['run_id'], endpoint, body, calls, controller


def _replace_payload(database, run_id, mutate, *, repair_record_hash=False):
    with sqlite3.connect(database) as connection:
        row = connection.execute('SELECT payload FROM nico_comprehensive_runs WHERE run_id=?', (run_id,)).fetchone()
        record = decode_run_storage(json.loads(row[0]))
        mutate(record)
        if repair_record_hash:
            record['integrity_sha256'] = _record_hash(record)
        connection.execute('UPDATE nico_comprehensive_runs SET payload=? WHERE run_id=?',
                           (encode_run_storage(record), run_id))


def test_repeat_exact_retained_pdf_reuses_completed_validation_without_mutable_response(retained):
    database, run_id, endpoint, expected, calls, _ = retained
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    first = endpoint(run_id, 'en')
    expected_headers = dict(first.headers)
    first.headers['x-nico-commit-sha'] = 'changed-response-object'
    second = endpoint(run_id, 'en')
    assert second is not first
    assert first.body == second.body == expected
    assert dict(second.headers) == expected_headers
    assert second.headers['x-nico-client-delivery-allowed'] == 'false'
    assert len(calls) == 1, 'unchanged completed validation should be reused on the repeat'
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_changed_unrelated_stage_cannot_reuse_old_pdf_proof(retained):
    database, run_id, endpoint, _, calls, _ = retained
    endpoint(run_id, 'en')
    _replace_payload(database, run_id, lambda record: record['stage_results'].update(
        {'unrelated_source_evidence': {'status': 'complete', 'changed': True}}))
    with pytest.raises(HTTPException) as failure:
        endpoint(run_id, 'en')
    assert failure.value.status_code == 409
    assert 'integrity_hash_mismatch' in failure.value.detail['reason']
    assert len(calls) == 2


def test_changed_independent_history_commitment_cannot_reuse_old_pdf_proof(retained):
    database, run_id, endpoint, _, calls, _ = retained
    endpoint(run_id, 'en')
    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE nico_comprehensive_review_history_commitments SET chain_sha256=? WHERE run_id=?',
                           ('f' * 64, run_id))
    with pytest.raises(HTTPException) as failure:
        endpoint(run_id, 'en')
    assert failure.value.status_code == 409
    assert failure.value.detail['reason'] == 'review_history_commitment_prefix_mismatch'
    assert len(calls) == 2


@pytest.mark.parametrize('change', ['missing', 'corrupt', 'wrong_digest', 'stale_approval'])
def test_changed_artifact_or_approval_reenters_original_validation(retained, change):
    database, run_id, endpoint, _, calls, _ = retained
    endpoint(run_id, 'en')

    def mutate(record):
        package = record['stage_results']['final_comprehensive_report_generation']['report_package']
        if change == 'missing':
            package.pop('pdf_base64')
        elif change == 'corrupt':
            package['pdf_base64'] = base64.b64encode(b'not PDF').decode()
        elif change == 'wrong_digest':
            package['pdf_sha256'] = 'f' * 64
        else:
            record.update(status='approved', human_review_completed=False)

    _replace_payload(database, run_id, mutate, repair_record_hash=True)
    with pytest.raises((ValueError, HTTPException)):
        endpoint(run_id, 'en')
    assert len(calls) == 2


def test_row_metadata_change_forces_fresh_validation(retained):
    database, run_id, endpoint, expected, calls, _ = retained
    endpoint(run_id, 'en')
    with sqlite3.connect(database) as connection:
        connection.execute('UPDATE nico_comprehensive_runs SET revision=revision+1 WHERE run_id=?', (run_id,))
    assert endpoint(run_id, 'en').body == expected
    assert len(calls) == 2


def test_missing_run_retains_normal_404(retained):
    _, _, endpoint, _, _, _ = retained
    with pytest.raises(HTTPException) as failure:
        endpoint('comprun_missing', 'en')
    assert failure.value.status_code == 404
    assert failure.value.detail['reason'] == 'comprehensive_run_not_found'


def test_new_controller_and_store_do_not_inherit_old_runtime_proof(retained):
    database, run_id, endpoint, expected, calls, _ = retained
    endpoint(run_id, 'en')
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database))
    controller = ComprehensiveApiController(ComprehensiveRunService(store, {}))
    response = controller.retained_pdf_read_only(run_id, 'en', locale.build_same_run_locale_pdf_response)
    assert response.body == expected
    assert len(calls) == 2


def test_live_codec_limit_change_cannot_reuse_old_validation(retained, monkeypatch):
    from nico import comprehensive_run_storage_codec_v1 as codec
    _, run_id, endpoint, _, calls, _ = retained
    endpoint(run_id, 'en')
    monkeypatch.setattr(codec, 'MAX_UNCOMPRESSED_BYTES', 1024)
    with pytest.raises(HTTPException) as failure:
        endpoint(run_id, 'en')
    assert failure.value.status_code == 409
    assert failure.value.detail['reason'] == 'run_storage_uncompressed_size_invalid'
    assert len(calls) == 2


def test_live_source_gate_change_cannot_reuse_old_validation(retained, monkeypatch):
    _, run_id, endpoint, _, calls, _ = retained
    endpoint(run_id, 'en')

    def reject(*_args, **_kwargs):
        raise ValueError('owned changed projection policy')

    monkeypatch.setattr(locale, '_frozen_source_pdf_response', reject)
    with pytest.raises(HTTPException) as failure:
        endpoint(run_id, 'en')
    assert failure.value.status_code == 409
    assert failure.value.detail['reason'] == 'owned changed projection policy'
    assert len(calls) == 2


def test_cache_version_change_forces_fresh_validation(retained, monkeypatch):
    from nico import retained_pdf_exact_input_cache_v1 as cache
    _, run_id, endpoint, expected, calls, _ = retained
    endpoint(run_id, 'en')
    monkeypatch.setattr(cache, 'VERSION', 'owned next implementation')
    assert endpoint(run_id, 'en').body == expected
    assert len(calls) == 2


def test_uncompressed_legacy_rows_remain_uncached(retained):
    database, run_id, endpoint, expected, calls, _ = retained
    with sqlite3.connect(database) as connection:
        row = connection.execute('SELECT payload FROM nico_comprehensive_runs WHERE run_id=?', (run_id,)).fetchone()
        record = decode_run_storage(json.loads(row[0]))
        connection.execute('UPDATE nico_comprehensive_runs SET payload=? WHERE run_id=?',
                           (json.dumps(record, ensure_ascii=False), run_id))
    assert endpoint(run_id, 'en').body == endpoint(run_id, 'en').body == expected
    assert len(calls) == 2


def test_missing_history_commitment_takes_original_backfill_path(retained):
    database, run_id, endpoint, expected, calls, _ = retained
    endpoint(run_id, 'en')
    with sqlite3.connect(database) as connection:
        connection.execute('DELETE FROM nico_comprehensive_review_history_commitments WHERE run_id=?', (run_id,))
    assert endpoint(run_id, 'en').body == expected
    # Original backfill calls the existing decoder twice; it is not a cache hit.
    assert len(calls) == 3


def test_pdf_builder_runs_after_sql_connection_closes(retained, monkeypatch):
    _, run_id, endpoint, expected, _, controller = retained
    store = controller._service._store
    original_factory = store._connection_factory
    opened = []

    class ObservedConnection:
        def __init__(self):
            self.inner = original_factory()
            opened.append(self)
        def cursor(self):
            return self.inner.cursor()
        def commit(self):
            return self.inner.commit()
        def rollback(self):
            return self.inner.rollback()
        def close(self):
            self.inner.close()
            opened.remove(self)

    original_builder = locale.build_same_run_locale_pdf_response

    def observe_builder(status, language):
        assert not opened, 'PDF preparation must not retain the DB connection'
        return original_builder(status, language)

    monkeypatch.setattr(store, '_connection_factory', ObservedConnection)
    monkeypatch.setattr(locale, 'build_same_run_locale_pdf_response', observe_builder)
    assert endpoint(run_id, 'en').body == expected
    assert not opened


def test_invalidated_warm_ticket_cannot_mint_under_old_input_after_policy_aba(retained, monkeypatch):
    from nico import retained_pdf_exact_input_cache_v1 as cache
    database, run_id, endpoint, expected, calls, _ = retained
    endpoint(run_id, 'en')
    original_finish = cache.finish_retained_pdf
    original_version = cache.VERSION
    observed = []

    def invalidate_then_rebuild(prepared, build):
        assert prepared.cached is not None
        original_entry = cache._entries[prepared.key][0]
        cache.VERSION = 'owned temporary policy'

        def mutate(record):
            package = record['stage_results']['final_comprehensive_report_generation']['report_package']
            changed_pdf = expected + b'\n'
            package['pdf_base64'] = base64.b64encode(changed_pdf).decode()
            package['pdf_sha256'] = hashlib.sha256(changed_pdf).hexdigest()

        _replace_payload(database, run_id, mutate, repair_record_hash=True)

        def rebuild_with_policy_returning_to_original():
            response = build()
            cache.VERSION = original_version
            return response

        try:
            response = original_finish(prepared, rebuild_with_policy_returning_to_original)
            observed.append(cache._entries[prepared.key][0])
            assert observed[-1] is original_entry, 'fresh input must never be minted under an invalidated warm ticket'
            assert observed[-1].body == expected
            return response
        finally:
            cache.VERSION = original_version

    monkeypatch.setattr(cache, 'finish_retained_pdf', invalidate_then_rebuild)
    assert endpoint(run_id, 'en').body == expected + b'\n'
    assert len(calls) == 2
    assert len(observed) == 1
