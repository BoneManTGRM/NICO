"""Owned synthetic full-path proof; no assessment, rollout, schema init or production replay."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore
import time
from uuid import uuid4

# Reuse the existing proof's fail-closed loopback-only target validation and
# inherited production-variable scrub before loading any runtime modules.
from scripts.postgres_review_pdf_preparation_proof import existing_adapter

os.environ['NICO_ENABLE_REVIEW_PDF_PREPARATION'] = 'false'
os.environ['NICO_REVIEW_PDF_PG_QUALIFIED'] = 'false'
os.environ['NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION'] = 'false'


def build_owned_record():
    from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_same_run_locale_report_v1 import canonical_sha256
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    from nico.comprehensive_run_record import create_comprehensive_run_record, apply_comprehensive_stage_result
    _install_production_wrappers()
    run_id = 'comprun_synthetic_pdf_' + uuid4().hex
    identity = dict(run_id=run_id, repository='synthetic/review-pdf-lifecycle',
        commit_sha='7'*40, evidence_ledger_id='ledger_'+run_id,
        customer_id='synthetic-pdf-'+uuid4().hex, project_id='synthetic-pdf-project')
    package = _package('en')
    package['json']['identity'].update(identity)
    reports = rebuild_client_artifacts(package)
    reports['report_id'] = 'report_'+run_id
    reports['canonical_truth_sha256'] = canonical_sha256(reports['json'])
    record = create_comprehensive_run_record(**identity, authorized=True)
    # These are explicitly synthetic stage inputs, never executor results from
    # an assessment. The real transition/integrity APIs establish the new record.
    for stage in COMPREHENSIVE_STAGES:
        result = {'status': 'complete', 'synthetic_fixture': True}
        if stage == 'final_comprehensive_report_generation': result['report_package'] = reports
        record = apply_comprehensive_stage_result(record, stage_id=stage, result=result)
    return record


def controller_for(store):
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_service import ComprehensiveRunService
    return ComprehensiveApiController(ComprehensiveRunService(store, {}))


def runtime_for(adapter):
    from tests.test_cross_locale_pdf_repeatability_v1 import _install_production_wrappers
    _install_production_wrappers()
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.review_pdf_preparation_jobs_v1 import PostgresReviewPdfPreparationJobs
    from nico.review_pdf_preparation_service_v1 import RetainedSourceAuthority, ReviewPdfPreparationService
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime, runtime_policy
    from nico.review_pdf_preparation_worker_v1 import run_worker
    store = ComprehensiveRunStore(lambda: adapter._psycopg.connect(adapter.database_url), dialect='postgres')
    source = RetainedSourceAuthority(store, controller_for(store), runtime_policy)
    def bounded_actual_child(*args, **kwargs):
        kwargs['max_seconds'] = min(kwargs['max_seconds'], 60)
        return run_worker(*args, **kwargs)
    service = ReviewPdfPreparationService(PostgresReviewPdfPreparationJobs(adapter), source,
        capacity=BoundedSemaphore(1), worker=bounded_actual_child)
    return PreparationRuntime(service)


def fresh_read(expected):
    runtime = runtime_for(existing_adapter())
    identity = expected['identity']
    response = runtime.retrieve(identity['run_id'], identity['language'], expected['job_id'], expected['binding'])
    assert hashlib.sha256(response.body).hexdigest() == expected['pdf_sha256']
    assert len(response.body) == expected['pdf_bytes']
    assert response.headers['x-nico-run-id'] == identity['run_id']
    assert response.headers['x-nico-commit-sha'] == identity['commit_sha']
    assert response.headers['x-nico-canonical-truth-sha256'] == identity['canonical_truth_sha256']
    assert response.headers['x-nico-report-language'] == identity['language']
    assert response.headers['x-nico-pdf-sha256'] == expected['pdf_sha256']
    assert response.headers['x-nico-client-delivery-allowed'] == 'false'
    assert response.headers['x-nico-approval-status'] == 'pending_human_approval'
    assert response.headers['x-nico-delivery-status'] == 'blocked_pending_human_approval'
    runtime.close()
    return {'fresh_process_retrieved_exact_bytes': True, 'identity_hash_and_gates_verified': True}


def proof(progress=None):
    progress = {} if progress is None else progress
    checks = progress.setdefault("checks", {})
    progress["phase"] = "existing_fixture_database"
    from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
    adapter = existing_adapter()
    # Existing infrastructure only. A missing table fails, never initializes schema.
    with adapter._connect() as con:
        for table in ('nico_comprehensive_runs', 'nico_comprehensive_review_history_commitments', 'client_jobs'):
            assert con.execute('SELECT to_regclass(%s) AS name', (table,)).fetchone()['name']
    release = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    os.environ['RAILWAY_GIT_COMMIT_SHA'] = release
    started_wall, started_cpu = time.monotonic(), time.process_time()
    progress["phase"] = "build_owned_source"
    record = build_owned_record()
    runtime = runtime_for(adapter)
    store = runtime.source.store
    # create() generates the genuine independent commitment for this NEW fixture.
    persisted = store.create(record)
    restored = store.load(record['identity']['run_id'])
    assert restored == persisted
    status = runtime.source.controller._status_artifact_from_record(restored)
    reports = status['reports']
    binding = dict(commit_sha=status['commit_sha'], canonical_truth_sha256=reports['canonical_truth_sha256'])
    progress["phase"] = "admit_and_render"
    queued = runtime.prepare(status['run_id'], 'es-MX', binding)
    identity, job = runtime._job(status['run_id'], 'es-MX', queued['job_id'], binding)
    source_before = runtime.source.capture(identity)
    ready = runtime.service.run_once(identity)
    assert ready['status'] == 'ready' and ready['client_delivery_allowed'] is False
    progress["phase"] = "same_process_retrieve"
    response = runtime.retrieve(identity.run_id, identity.language, identity.job_id, binding)
    assert response.body.startswith(b'%PDF')
    expected = dict(identity=asdict(identity), job_id=identity.job_id, binding=binding,
        pdf_sha256=hashlib.sha256(response.body).hexdigest(), pdf_bytes=len(response.body))
    assert ready['pdf_sha256'] == expected['pdf_sha256']
    assert runtime.source.capture(identity) == source_before
    assert store.load(identity.run_id) == persisted
    runtime.close()
    del runtime, store
    checks.update(real_store_restore=True, real_child_render=True, locked_ready_publication=True,
        source_and_history_unchanged_during_preparation=True)
    progress["phase"] = "fresh_process_retrieve"
    child = subprocess.run([sys.executable, __file__, '--read'], input=json.dumps(expected),
        text=True, capture_output=True, timeout=60)
    assert child.returncode == 0, child.stderr[-2000:]
    checks.update(json.loads(child.stdout))
    progress["phase"] = "negative_controls"
    runtime = runtime_for(existing_adapter())
    # Existing source revision identity fencing; no source bytes are edited.
    from dataclasses import replace
    try: runtime.source.capture(replace(identity, source_revision=identity.source_revision+1))
    except PreparationConflict: checks['stale_source_rejected'] = True
    else: raise AssertionError('stale source accepted')
    try: runtime.jobs.heartbeat(identity, 'stale-synthetic-owner')
    except PreparationConflict: checks['stale_owner_rejected'] = True
    else: raise AssertionError('stale owner accepted')
    # A second locale identity exercises real cancellation without another render.
    cancelled_identity = replace(identity, language='en')
    runtime.jobs.enqueue(cancelled_identity, preparation_authorized=True)
    runtime.cancel(cancelled_identity.run_id, cancelled_identity.language, cancelled_identity.job_id, binding)
    assert runtime.service.run_once(cancelled_identity) is None
    assert runtime.jobs.get(cancelled_identity)['status'] == 'cancelled'
    checks['cancelled_job_not_rendered'] = True
    # A real, revisioned mutation of this owned fixture must invalidate retrieval.
    from nico.comprehensive_run_record import _record_hash
    mutated = runtime.source.store.load(identity.run_id)
    old_revision = mutated['revision']
    mutated['revision'] += 1
    mutated['synthetic_negative_control'] = 'changed source after retained publication'
    mutated['integrity_sha256'] = _record_hash(mutated)
    runtime.source.store.save(mutated, expected_revision=old_revision)
    try: runtime.retrieve(identity.run_id, identity.language, identity.job_id, binding)
    except PreparationConflict: checks['mutated_source_cannot_retrieve_old_pdf'] = True
    else: raise AssertionError('changed source retrieved retained PDF')
    assert all(os.environ.get(key) == 'false' for key in (
        'NICO_ENABLE_REVIEW_PDF_PREPARATION', 'NICO_REVIEW_PDF_PG_QUALIFIED',
        'NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION'))
    checks.update(real_store_restore=True, real_child_render=True, locked_ready_publication=True,
        source_and_history_unchanged_during_preparation=True, feature_flags_off=True)
    runtime.close()
    progress['phase'] = 'complete'
    return dict(status='passed', synthetic=True, live_production_claim=False,
        actual_retained_report_timing=False, assessment_executed=False, client_delivery_allowed=False,
        commit_sha=release, source_commit_sha=identity.commit_sha, pdf_sha256=expected['pdf_sha256'],
        pdf_bytes=expected['pdf_bytes'], checks=checks,
        wall_seconds=round(time.monotonic()-started_wall,3), parent_cpu_seconds=round(time.process_time()-started_cpu,3))


def write_proof(output):
    """Retain bounded failure evidence without exception text or source contents."""
    progress = {'phase': 'starting', 'checks': {}}
    wall, cpu = time.monotonic(), time.process_time()
    try:
        result = proof(progress)
    except Exception as exc:
        result = dict(status='failed', synthetic=True, live_production_claim=False,
            actual_retained_report_timing=False, assessment_executed=False,
            client_delivery_allowed=False, phase=progress['phase'], checks=progress['checks'],
            error_type=type(exc).__name__,
            wall_seconds=round(time.monotonic()-wall, 3),
            parent_cpu_seconds=round(time.process_time()-cpu, 3))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2)+'\n')
        raise
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--read', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.read:
        print(json.dumps(fresh_read(json.load(sys.stdin))))
    else:
        if args.output is None: parser.error('--output required')
        write_proof(args.output)
