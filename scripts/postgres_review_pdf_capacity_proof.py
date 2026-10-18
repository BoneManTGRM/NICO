"""One-artifact capacity proof for the existing synthetic CI Postgres service only.

No production target, retained-row deletion or automatic orphan recovery.
Positive lifecycle uses an isolated schema in the explicitly guarded CI service. Run BEFORE the other review-PDF proofs populate client_jobs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, replace
import hashlib
import io
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from uuid import uuid4

REQUIRED_CHECKS = (
    'independent_processes_wait_on_global_before_identity', 'one_distinct_identity_admitted',
    'duplicate_admission_idempotent', 'legacy_and_terminal_rows_counted',
    'malformed_namespace_and_legacy_workflow_counted', 'exact_66mib_and_one_byte_overflow',
    'negative_controls_rolled_back_without_deletion', 'expired_live_owner_not_reclaimed',
    'concurrent_late_publications_fenced', 'cancellation_while_child_alive_preserves_occupancy',
    'crash_without_receipt_stays_blocked', 'stale_ownership_rejected',
    'one_row_retained_no_replacement', 'rollout_flags_off',
)

EXPECTED_TARGET = 'postgresql://nico:nico@127.0.0.1:5432/nico'  # Public ephemeral CI fixture.


def require_context(explicit):
    if (explicit is not True or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('CI') != 'true'
            or os.environ.get('GITHUB_WORKFLOW') != 'Postgres Restart Proof'
            or os.environ.get('GITHUB_REPOSITORY') != 'BoneManTGRM/NICO'
            or os.environ.get('GITHUB_EVENT_NAME') not in {'pull_request', 'push', 'workflow_dispatch'}
            or not os.environ.get('GITHUB_RUN_ID', '').isdigit()
            or not os.environ.get('GITHUB_RUN_ATTEMPT', '').isdigit()
            or os.environ.get('NICO_TEST_DATABASE_URL') != EXPECTED_TARGET):
        raise ValueError('explicit_synthetic_ci_context_required')


def existing_jobs(explicit):
    require_context(explicit)  # Reject BEFORE any connector/runtime import or connection.
    for key in ('NICO_ENABLE_REVIEW_PDF_PREPARATION', 'NICO_REVIEW_PDF_PG_QUALIFIED',
                'NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION'):
        os.environ[key] = 'false'
    from scripts.postgres_review_pdf_preparation_proof import existing_adapter
    from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlyPostgresJobs
    # existing_adapter scrubs inherited production aliases and rejects non-loopback URLs.
    return QualificationOnlyPostgresJobs(existing_adapter())


def validate_fixture(identity):
    if (not identity.customer_id.startswith('capacity-proof-')
            or not identity.run_id.startswith('comprun_capacity_')
            or identity.repository != 'synthetic/capacity-proof'
            or identity.commit_sha != '7'*40):
        raise ValueError('owned_synthetic_capacity_identity_required')


def publish_candidate(jobs, identity, owner):
    """Publication race at the real ledger fence; full source checks live in lifecycle proof."""
    import base64
    from pypdf import PdfWriter
    from nico.review_pdf_preparation_worker_v1 import validate_result
    writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
    stream = io.BytesIO(); writer.write(stream)
    pdf = stream.getvalue(); digest = hashlib.sha256(pdf).hexdigest()
    headers = {'x-nico-run-id': identity.run_id, 'x-nico-commit-sha': identity.commit_sha,
        'x-nico-report-language': identity.language,
        'x-nico-canonical-truth-sha256': identity.canonical_truth_sha256,
        'x-nico-assessment-rerun': 'false', 'x-nico-approval-status': 'pending_human_approval',
        'x-nico-client-delivery-allowed': 'false', 'x-nico-delivery-status': 'blocked_pending_human_approval',
        'x-nico-localized-artifact-requires-new-approval': 'true',
        'x-nico-localized-artifact-approval-invalidated': 'true', 'x-nico-artifact-finality': 'automated_draft',
        'x-nico-review-pdf-artifact-mode': identity.artifact_mode,
        'x-nico-pdf-sha256': digest, 'x-nico-artifact-sha256': digest}
    result = dict(pdf_base64=base64.b64encode(pdf).decode(), headers=headers,
                  identity=asdict(identity), validated_page_count=1)
    validate_result(result, identity)
    with jobs._transaction(identity) as con:
        job, now = jobs._owned(con, identity, owner)
        job.update(status='ready', updated_epoch=now, pdf_base64=result['pdf_base64'],
                   result_headers=headers, pdf_sha256=digest, validated_page_count=1,
                   result_owner=owner, lease_id='', lease_until_epoch=0)
        jobs._write(con, identity, job)
    return job


def child(explicit):
    jobs = existing_jobs(explicit)
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity, PreparationConflict
    request = json.loads(sys.stdin.readline(16384))
    identity = PreparationIdentity(**request['identity']); validate_fixture(identity)
    con = jobs.adapter._connect()
    pid = con.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']; con.commit()
    jobs.adapter._connect = lambda: con  # Exactly one operation/transaction in this child.
    print(json.dumps({'event':'ready', 'pid':pid}), flush=True)
    if sys.stdin.readline(16).strip() != 'go':
        con.close(); raise ValueError('synthetic_start_required')
    try:
        action = request['action']
        if action == 'enqueue':
            job = jobs.enqueue(identity, preparation_authorized=True)
        elif action == 'claim':
            job = jobs.claim(identity)
        elif action == 'hold':
            job = jobs.claim(identity)
            if job is None: raise RuntimeError('synthetic_owner_missing')
        elif action == 'publish':
            job = publish_candidate(jobs, identity, request['owner'])
        elif action == 'cancel':
            from types import SimpleNamespace
            from nico.review_pdf_preparation_api_v1 import PreparationRuntime
            runtime = PreparationRuntime(SimpleNamespace(jobs=jobs, source=None))
            # Fixture-only identity already checked; this is not HTTP/auth qualification.
            runtime._job = lambda *args, **kw: (identity, None)
            runtime.cancel(identity.run_id, identity.language, identity.job_id, {})
            print(json.dumps({'event':'result','cancelled':True}), flush=True)
            return
        else:
            raise ValueError('synthetic_action_invalid')
        print(json.dumps({'event':'result', 'accepted':job is not None,
            'job_id':identity.job_id, 'status':job['status'] if job else None,
            'owner':job['lease_id'] if action == 'hold' and job else None}), flush=True)
        if action == 'hold':
            # Controlled physical process remains alive, without claiming actual rendering.
            sys.stdin.readline(16)
    except PreparationConflict:
        print(json.dumps({'event':'result','rejected':True}), flush=True)


def read_event(process, timeout=10):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout): raise RuntimeError('synthetic_child_timeout')
        line = process.stdout.readline(16384)
    if not line or len(line) >= 16384: raise RuntimeError('synthetic_child_output_invalid')
    return json.loads(line)


def spawn(identity, action, children, *, owner=None):
    p = subprocess.Popen([sys.executable, __file__, '--synthetic-ci-proof', '--child'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    children.append(p)
    p.stdin.write(json.dumps(dict(identity=asdict(identity), action=action, owner=owner))+'\n')
    p.stdin.flush()
    ready = read_event(p)
    if ready.get('event') != 'ready': raise RuntimeError('synthetic_child_not_ready')
    return p, ready['pid']


def start(process):
    process.stdin.write('go\n'); process.stdin.flush()


def finish(process):
    result = read_event(process)
    _, stderr = process.communicate(timeout=10)
    if process.returncode or stderr or result.get('event') != 'result':
        raise RuntimeError('synthetic_child_failed')
    return result


class _RollbackFixture(Exception):
    pass


@contextmanager
def rollback_fixture(jobs, identity):
    """Negative controls roll back owned fixture changes; never delete retained rows."""
    try:
        with jobs._transaction(identity) as con:
            yield con
            raise _RollbackFixture()
    except _RollbackFixture:
        pass


def check_storage_boundaries(jobs, winner, checks, observations=None):
    observations = [] if observations is None else observations
    from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
    from nico.review_pdf_single_artifact_qualification_v1 import MAX_SERIALIZED_BYTES, serialized_size
    original = jobs.get(winner)
    other = replace(winner, project_id='synthetic-negative')
    candidate = dict(original, job_id=other.job_id, identity=asdict(other))
    candidate.pop('qualification')  # Must otherwise be a valid fresh admission.

    for state in ('queued','rendering','ready','failed','cancelled','budget_exhausted','legacy_unknown'):
        with rollback_fixture(jobs, other) as con:
            payload = dict(original, status=state); payload.pop('qualification')
            con.execute('UPDATE client_jobs SET status=%s,payload=%s WHERE job_id=%s AND customer_id=%s',
                (state, jobs.adapter._jsonb(payload), winner.job_id, winner.customer_id))
            try: jobs._write(con, other, dict(candidate))
            except PreparationConflict as error:
                assert str(error)=='qualification_one_artifact_full'
            else: raise AssertionError('terminal_or_legacy_capacity_not_counted')
        observations.append({'retention_state':state,'new_identity_rejected':True})
    checks['legacy_and_terminal_rows_counted'] = True
    for key, payload in (('reviewpdfprep_legacy_'+uuid4().hex, 'malformed fixture payload'),
                         ('old_capacity_'+uuid4().hex, {'workflow':'review_pdf_preparation.v0'})):
        with rollback_fixture(jobs, other) as con:
            con.execute('UPDATE client_jobs SET job_id=%s,payload=%s WHERE job_id=%s AND customer_id=%s',
                (key, jobs.adapter._jsonb(payload), winner.job_id, winner.customer_id))
            try: jobs._write(con, other, dict(candidate))
            except PreparationConflict as error:
                assert str(error)=='qualification_one_artifact_full'
            else: raise AssertionError('malformed_or_legacy_namespace_ignored')
        observations.append({'legacy_control':'reserved_namespace' if isinstance(payload,str) else 'workflow',
                             'new_identity_rejected':True})
    checks['malformed_namespace_and_legacy_workflow_counted'] = True
    with rollback_fixture(jobs, winner) as con:
        padded = dict(original, fixture_padding='')
        padded['fixture_padding'] = 'x'*(MAX_SERIALIZED_BYTES-serialized_size(padded))
        assert serialized_size(padded) == MAX_SERIALIZED_BYTES
        jobs._write(con, winner, padded)
        assert serialized_size(jobs._read(con, winner)) == MAX_SERIALIZED_BYTES
        padded['fixture_padding'] += 'x'
        try: jobs._write(con, winner, padded)
        except PreparationConflict as error:
            assert str(error)=='qualification_serialized_limit'
        else: raise AssertionError('serialized_capacity_exceeded')
        assert serialized_size(jobs._read(con, winner)) == MAX_SERIALIZED_BYTES
    checks['exact_66mib_and_one_byte_overflow'] = True
    observations.append({'serialized_bytes':MAX_SERIALIZED_BYTES,'one_byte_overflow_rejected':True})
    assert jobs.get(winner) == original
    checks['negative_controls_rolled_back_without_deletion'] = True


# Fixture isolation only: production tables and advisory-lock semantics are unchanged.
# No public fallback in search_path and no retained rows are deleted or reset.
FIXTURE_TABLES = ('client_jobs', 'nico_comprehensive_runs',
    'nico_comprehensive_review_history_commitments', 'nico_comprehensive_browser_projections',
    'nico_comprehensive_final_report_jobs')
POSITIVE_CHECKS = (
    'real_source_and_history_restored', 'real_child_rendered_with_occupancy_held',
    'occupancy_held_through_physical_cleanup', 'cleanup_receipt_released_execution_only',
    'capacity_enabled_ready_publication', 'fresh_process_retrieved_exact_bytes',
    'identity_hash_and_gates_verified', 'retained_reservation_blocks_new_identity',
    'existing_pdf_retrievable_after_rejected_admission', 'source_and_history_unchanged',
    'result_and_serialized_bounds_preserved',
)


def isolated_adapter(explicit, schema, *, create=False):
    require_context(explicit)
    import re
    if not re.fullmatch(r'capacity_positive_[0-9a-f]{32}', schema):
        raise ValueError('owned_synthetic_schema_required')
    # This sets flags OFF and scrubs inherited production connection aliases.
    adapter = existing_jobs(explicit).adapter
    from psycopg import sql
    if create:
        with adapter._connect() as con:
            assert con.execute('SELECT current_database() AS db,current_user AS owner,pg_is_in_recovery() AS recovery').fetchone() == {
                'db':'nico', 'owner':'nico', 'recovery':False}
            con.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            for table in FIXTURE_TABLES:
                con.execute(sql.SQL('CREATE TABLE {}.{} (LIKE public.{} INCLUDING ALL)').format(
                    sql.Identifier(schema), sql.Identifier(table), sql.Identifier(table)))
    from types import SimpleNamespace
    driver = adapter._psycopg
    def connect(url, **kwargs):
        # Every ledger/source connection, including tuple-row source restoration,
        # goes to this exact CI fixture and schema. Never inherit caller options.
        require_context(explicit)
        from nico.postgres_timeout_patch import postgres_connect_kwargs
        options = kwargs.pop('options', '')
        if url != EXPECTED_TARGET or options not in ('', postgres_connect_kwargs()['options']):
            raise ValueError('synthetic_schema_connection_required')
        return driver.connect(url, options=options+' -csearch_path='+schema+',pg_catalog', **kwargs)
    adapter._psycopg = SimpleNamespace(connect=connect)
    with adapter._connect() as con:
        assert con.execute('SELECT current_schema() AS name').fetchone()['name'] == schema
        for table in FIXTURE_TABLES:
            # No fallback to public if a fixture table is absent.
            assert con.execute('SELECT to_regclass(%s) AS name', (table,)).fetchone()['name']
    return adapter


def observed_jobs_class(base, checks):
    class ObservedJobs(base):
        def confirm_execution_exit(self, identity, owner, *, state, supervisor):
            before = self.get(identity)
            assert before['status'] == 'ready'
            assert before['qualification']['execution_state'] == 'held'
            assert state['physical_worker_exit_confirmed'] is True
            assert state['temporary_files_cleanup_confirmed'] is True
            assert all(guard.idle() for guard in state['pending_guards'])
            assert supervisor is not None and not supervisor.is_alive()
            super().confirm_execution_exit(identity, owner, state=state, supervisor=supervisor)
            after = self.get(identity)
            expected = dict(before, updated_epoch=after['updated_epoch'],
                qualification=dict(before['qualification'], execution_state='released'))
            assert after == expected
            checks['cleanup_receipt_released_execution_only'] = True
    return ObservedJobs


def observe_worker(runtime, checks):
    actual_worker = runtime.service.worker
    def observed_worker(status, identity, **kwargs):
        state = kwargs['state']; heartbeat = kwargs['heartbeat']
        def observed_heartbeat(**phase):
            assert state['physical_worker_exit_confirmed'] is False
            assert state['temporary_files_cleanup_confirmed'] is False
            assert runtime.jobs.get(identity)['qualification']['execution_state'] == 'held'
            heartbeat(**phase)
            checks['real_child_rendered_with_occupancy_held'] = True
        kwargs['heartbeat'] = observed_heartbeat
        result = actual_worker(status, identity, **kwargs)
        # Actual worker returns only after child termination and private-file cleanup.
        assert state['physical_worker_exit_confirmed'] is True
        assert state['temporary_files_cleanup_confirmed'] is True
        assert runtime.jobs.get(identity)['qualification']['execution_state'] == 'held'
        checks['occupancy_held_through_physical_cleanup'] = True
        return result
    runtime.service.worker = observed_worker
    return runtime


def qualified_runtime(adapter, checks=None):
    from scripts.postgres_review_pdf_lifecycle_proof import runtime_for
    from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlyPostgresJobs
    factory = (QualificationOnlyPostgresJobs if checks is None
               else observed_jobs_class(QualificationOnlyPostgresJobs, checks))
    runtime = runtime_for(adapter, jobs_factory=factory)
    return runtime if checks is None else observe_worker(runtime, checks)


def positive_read(expected, *, explicit):
    require_context(explicit)
    from scripts.postgres_review_pdf_lifecycle_proof import fresh_read
    from nico.review_pdf_single_artifact_qualification_v1 import QualificationOnlyPostgresJobs
    adapter = isolated_adapter(explicit, expected['schema'])
    return fresh_read(expected, adapter=adapter, jobs_factory=QualificationOnlyPostgresJobs)


def positive_lifecycle(progress, *, explicit):
    from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record
    from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
    from nico.review_pdf_single_artifact_qualification_v1 import MAX_SERIALIZED_BYTES, serialized_size
    checks = progress['checks']
    progress['phase'] = 'positive_isolated_fixture_schema'
    schema = 'capacity_positive_'+uuid4().hex
    adapter = isolated_adapter(explicit, schema, create=True)
    release = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    os.environ['RAILWAY_GIT_COMMIT_SHA'] = release
    progress['phase'] = 'positive_real_source_and_history'
    record = build_owned_record()
    runtime = qualified_runtime(adapter, checks)
    try:
        store = runtime.source.store
        persisted = store.create(record)
        assert store.load(record['identity']['run_id']) == persisted
        status = runtime.source.controller._status_artifact_from_record(persisted)
        binding = dict(commit_sha=status['commit_sha'], canonical_truth_sha256=status['reports']['canonical_truth_sha256'])
        queued = runtime.prepare(status['run_id'], 'es-MX', binding)
        identity, _ = runtime._job(status['run_id'], 'es-MX', queued['job_id'], binding)
        before = runtime.source.capture(identity)
        with adapter._connect() as con:
            history_before = con.execute('SELECT * FROM nico_comprehensive_review_history_commitments WHERE run_id=%s', (identity.run_id,)).fetchone()
        assert history_before is not None
        checks['real_source_and_history_restored'] = True
        progress['phase'] = 'positive_actual_render_and_locked_publication'
        ready = runtime.service.run_once(identity)
        assert ready['status'] == 'ready' and ready['client_delivery_allowed'] is False
        retained = runtime.jobs.get(identity)
        assert retained['status'] == 'ready' and retained['qualification']['execution_state'] == 'released'
        assert checks.get('cleanup_receipt_released_execution_only') is True
        assert runtime.service.capacity.acquire(blocking=False)
        runtime.service.capacity.release()
        checks['capacity_enabled_ready_publication'] = True
        progress['phase'] = 'positive_verified_retrieval'
        response = runtime.retrieve(identity.run_id, identity.language, identity.job_id, binding)
        expected = dict(schema=schema, identity=asdict(identity), job_id=identity.job_id, binding=binding,
            pdf_sha256=hashlib.sha256(response.body).hexdigest(), pdf_bytes=len(response.body))
        assert expected['pdf_sha256'] == retained['pdf_sha256']
        assert expected['pdf_bytes'] > 0
        assert len(retained['pdf_base64']) <= 64*1024*1024
        assert serialized_size(retained) <= MAX_SERIALIZED_BYTES
        assert retained['qualification']['reserved_bytes'] == MAX_SERIALIZED_BYTES
        checks['result_and_serialized_bounds_preserved'] = True
        assert runtime.jobs.enqueue(identity, preparation_authorized=True) == retained
        assert runtime.jobs.claim(identity) is None
        try:
            runtime.jobs.enqueue(replace(identity, language='en'), preparation_authorized=True)
        except PreparationConflict as error:
            assert str(error) == 'qualification_one_artifact_full'
        else:
            raise AssertionError('released_execution_lost_retained_reservation')
        with runtime.jobs._transaction(identity) as con:
            assert runtime.jobs._queue_ids(con) == [identity.job_id]
        assert runtime.jobs.get(identity) == retained
        checks['retained_reservation_blocks_new_identity'] = True
        # Re-run full authoritative retrieval after the rejected admission.
        assert runtime.retrieve(identity.run_id, identity.language, identity.job_id, binding).body == response.body
        checks['existing_pdf_retrievable_after_rejected_admission'] = True
        assert runtime.source.capture(identity) == before
        assert store.load(identity.run_id) == persisted
        with adapter._connect() as con:
            assert con.execute('SELECT * FROM nico_comprehensive_review_history_commitments WHERE run_id=%s', (identity.run_id,)).fetchone() == history_before
        checks['source_and_history_unchanged'] = True
    finally:
        runtime.close()
    progress['phase'] = 'positive_fresh_process_retrieval'
    reader = subprocess.run([sys.executable, __file__, '--synthetic-ci-proof', '--positive-read'],
        input=json.dumps(expected), text=True, capture_output=True, timeout=60)
    if reader.returncode or reader.stderr:
        raise RuntimeError('synthetic_positive_reader_failed')
    observed = json.loads(reader.stdout)
    assert observed == {'fresh_process_retrieved_exact_bytes':True, 'identity_hash_and_gates_verified':True}
    checks.update(observed)
    progress['observations'].append({'positive_pdf_sha256':expected['pdf_sha256'], 'positive_pdf_bytes':expected['pdf_bytes'],
        'reservation_bytes':MAX_SERIALIZED_BYTES, 'execution_state':'released', 'status':'ready'})


def proof(progress, *, explicit):
    jobs = existing_jobs(explicit)
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity, PreparationConflict
    from nico.review_pdf_single_artifact_qualification_v1 import GLOBAL_LOCK_KEY
    checks = progress['checks']; observations = progress['observations']; children = []
    nonce = uuid4().hex
    release = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    candidates = [PreparationIdentity('capacity-proof-'+nonce, 'synthetic-'+str(n),
        'comprun_capacity_'+nonce, 'synthetic/capacity-proof', '7'*40, 1,
        'a'*64, 'b'*64, 'c'*64, release, 'd'*64, 'es-MX', 'pending-source-localized-draft') for n in range(4)]
    try:
        progress['phase'] = 'existing_empty_queue_and_global_first_contention'
        with jobs._transaction(candidates[0]) as con:
            info = con.execute('SELECT current_database() AS db,current_user AS owner,pg_is_in_recovery() AS recovery').fetchone()
            assert info == {'db':'nico','owner':'nico','recovery':False}
            assert jobs._queue_ids(con) == []  # Never clean an occupied database to make proof pass.
            waiting = [spawn(i,'enqueue',children) for i in candidates]
            for p,_ in waiting: start(p)
            deadline = time.monotonic()+3
            pids = [pid for _,pid in waiting]
            key = GLOBAL_LOCK_KEY & ((1<<64)-1)
            while True:
                locks = con.execute("SELECT pid,classid,objid,objsubid,granted FROM pg_locks WHERE locktype='advisory' AND pid=ANY(%s)", (pids,)).fetchall()
                if (len(locks)==4 and all(not r['granted'] and int(r['classid'])==(key>>32)
                        and int(r['objid'])==(key & 0xffffffff) and r['objsubid']==1 for r in locks)):
                    break
                if time.monotonic()>=deadline: raise RuntimeError('global_first_lock_not_observed')
                time.sleep(.02)
            checks['independent_processes_wait_on_global_before_identity'] = True
        results = [finish(p) for p,_ in waiting]; observations.append({'distinct_admission':results})
        assert sum(r.get('accepted') is True for r in results)==1
        winner = candidates[next(n for n,r in enumerate(results) if r.get('accepted'))]
        checks['one_distinct_identity_admitted'] = True
        before_duplicates = jobs.get(winner)
        duplicates = [spawn(winner,'enqueue',children)[0] for _ in range(4)]
        for p in duplicates: start(p)
        repeated = [finish(p) for p in duplicates]; observations.append({'duplicate_admission':repeated})
        assert all(r.get('accepted') and r['job_id']==winner.job_id for r in repeated)
        assert jobs.get(winner)==before_duplicates and before_duplicates['attempts']==0
        checks['duplicate_admission_idempotent'] = True
        progress['phase'] = 'retention_and_serialization_boundaries'
        check_storage_boundaries(jobs,winner,checks,observations)
        progress['phase'] = 'physical_owner_alive_expiry_and_cancellation'
        holder,_ = spawn(winner,'hold',children); start(holder)
        lease = read_event(holder); assert lease.get('accepted') and holder.poll() is None
        owner = lease['owner']
        # Existing protocol-proof technique: expire only this uniquely owned fixture.
        with jobs._transaction(winner) as con:
            con.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{lease_until_epoch}','0'::jsonb) WHERE job_id=%s AND customer_id=%s",
                        (winner.job_id,winner.customer_id))
        claimant,_ = spawn(winner,'claim',children);start(claimant)
        assert finish(claimant).get('accepted') is False and holder.poll() is None
        assert jobs.get(winner)['qualification']['execution_state']=='held'
        checks['expired_live_owner_not_reclaimed'] = True
        races = [spawn(winner,'publish',children,owner=owner)[0] for _ in range(4)]
        canceller,_ = spawn(winner,'cancel',children)
        for p in [*races,canceller]: start(p)
        raced = [finish(p) for p in races]; cancelled=finish(canceller)
        observations.append({'late_publications':raced,'cancellation':cancelled})
        assert all(r.get('rejected') is True for r in raced) and cancelled.get('cancelled') is True
        retained=jobs.get(winner)
        assert holder.poll() is None and retained['status']=='cancelled'
        assert retained['qualification']['execution_state']=='held' and 'pdf_base64' not in retained
        checks['concurrent_late_publications_fenced'] = True
        checks['cancellation_while_child_alive_preserves_occupancy'] = True
        holder.terminate();holder.wait(timeout=5)
        # Physical death observed here is NOT an owner cleanup receipt. Do not clear it.
        claimant,_ = spawn(winner,'claim',children);start(claimant)
        assert finish(claimant).get('accepted') is False
        try: jobs.heartbeat(winner,'0'*32)
        except PreparationConflict: pass
        else: raise AssertionError('stale_owner_accepted')
        assert jobs.get(winner)==retained
        checks['crash_without_receipt_stays_blocked'] = True
        checks['stale_ownership_rejected'] = True
        with jobs._transaction(winner) as con:
            assert jobs._queue_ids(con)==[winner.job_id]
        checks['one_row_retained_no_replacement'] = True
        checks['rollout_flags_off'] = all(os.environ.get(key)=='false' for key in (
            'NICO_ENABLE_REVIEW_PDF_PREPARATION','NICO_REVIEW_PDF_PG_QUALIFIED',
            'NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION'))
        assert set(checks)==set(REQUIRED_CHECKS) and all(value is True for value in checks.values())
        positive_lifecycle(progress, explicit=explicit)
        assert all(os.environ.get(key)=='false' for key in (
            'NICO_ENABLE_REVIEW_PDF_PREPARATION','NICO_REVIEW_PDF_PG_QUALIFIED',
            'NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION'))
        assert set(checks) == set(REQUIRED_CHECKS) | set(POSITIVE_CHECKS)
        assert all(value is True for value in checks.values())
        progress['phase']='complete'
        return dict(status='passed',synthetic=True,live_production_claim=False,
            assessment_executed=False,client_delivery_allowed=False,commit_sha=release,
            qualified_scope='capacity_protocol_and_synthetic_lifecycle',successful_ready_publication_proven=True,
            checks=checks,observations=observations)
    finally:
        for p in children:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=3)
                except subprocess.TimeoutExpired: p.kill();p.wait(timeout=3)
            for pipe in (p.stdin,p.stdout,p.stderr):
                if pipe is not None: pipe.close()


def failure_site(error):
    """Repository code location only; never exception text, SQL parameters or locals."""
    allowed = {'postgres_review_pdf_capacity_proof.py', 'postgres_review_pdf_lifecycle_proof.py',
        'review_pdf_single_artifact_qualification_v1.py', 'review_pdf_preparation_jobs_v1.py'}
    site = {}
    tb = error.__traceback__
    while tb is not None:
        filename = Path(tb.tb_frame.f_code.co_filename).name
        if filename in allowed:
            site = {'file':filename, 'function':tb.tb_frame.f_code.co_name, 'line':tb.tb_lineno}
        tb = tb.tb_next
    return site


def write_proof(output, *, explicit):
    progress = {'phase':'context','checks':{},'observations':[]}
    started = time.monotonic()
    try:
        result = proof(progress,explicit=explicit)
    except BaseException as error:
        result = dict(status='failed',synthetic=True,live_production_claim=False,
            assessment_executed=False,client_delivery_allowed=False,error_type=type(error).__name__,
            failure_site=failure_site(error),**progress)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2)+'\n')
        raise RuntimeError('synthetic_capacity_proof_failed') from None
    result['wall_seconds']=round(time.monotonic()-started,3)
    encoded=json.dumps(result,indent=2)+'\n'
    if len(encoded)>32768: raise RuntimeError('capacity_evidence_not_bounded')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(encoded)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--synthetic-ci-proof',action='store_true')
    parser.add_argument('--child',action='store_true')
    parser.add_argument('--positive-read',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.positive_read:
        try:
            print(json.dumps(positive_read(json.load(sys.stdin), explicit=args.synthetic_ci_proof)))
        except BaseException as error:
            print(json.dumps({'event':'failed','error_type':type(error).__name__}),flush=True)
            raise SystemExit(1)
    elif args.child:
        try: child(args.synthetic_ci_proof)
        except BaseException as error:
            print(json.dumps({'event':'failed','error_type':type(error).__name__}),flush=True)
            raise SystemExit(1)
    else:
        if args.output is None: parser.error('--output required')
        write_proof(args.output,explicit=args.synthetic_ci_proof)
