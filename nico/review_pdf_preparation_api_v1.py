"""Opt-in pending-review preparation API. Default startup exposes no active worker."""
from __future__ import annotations

from contextlib import asynccontextmanager, nullcontext
from dataclasses import asdict
import hashlib
import json
import marshal
import os
import re
from uuid import uuid4
from threading import BoundedSemaphore, Event, Thread

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from nico.review_pdf_preparation_jobs_v1 import (
    PreparationIdentity, PreparationConflict, PostgresReviewPdfPreparationJobs, WORKFLOW,
)
from nico.review_pdf_preparation_service_v1 import (
    RetainedSourceAuthority, ReviewPdfPreparationService, _fingerprint,
)
from nico.review_pdf_artifact_policy_v1 import artifact_mode, VERSION as ARTIFACT_POLICY
from nico.review_pdf_preparation_worker_v1 import validate_result
from nico.review_pdf_canary_scope_v1 import CanaryScope
from nico.review_pdf_preparation_deadline_v1 import CommitOutcomeUnknown, DeadlineGuard

from nico.review_pdf_admission_observability_v1 import AdmissionTrace, phase

ROUTE = '/assessment/comprehensive-run/{run_id}/review-pdf/{language}'
_HEADERS = {'Cache-Control': 'no-store, private, max-age=0'}
_RUN = re.compile(r'comprun_[a-zA-Z0-9_-]{1,160}$')
_JOB = re.compile(r'reviewpdfprep_[0-9a-f]{64}$')


def runtime_policy():
    from nico.retained_pdf_exact_input_cache_v1 import _live_policy
    from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_pdf_response
    revision = os.getenv('RAILWAY_GIT_COMMIT_SHA', '').strip().lower()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise RuntimeError('review_pdf_renderer_revision_unavailable')
    values = []
    for value in _live_policy(build_same_run_locale_pdf_response):
        if callable(value):
            values.append([value.__module__, value.__qualname__,
                # Protocol 0 serializes the complete code object without the
                # reference-sharing flags that change when code attributes are
                # retained during rendering. The policy must survive a restart.
                hashlib.sha256(marshal.dumps(value.__code__, 0)).hexdigest()])
        else:
            values.append(value)
    return revision, _fingerprint(['review-pdf-api.v3', ARTIFACT_POLICY, revision, values])


class PreparationBusy(RuntimeError):
    pass


class PreparationRuntime:
    def __init__(self, service, *, canary_scope=None):
        self.canary_scope = canary_scope
        self.service = service
        self.jobs, self.source = service.jobs, service.source
        self.stop = Event()
        self.thread = None
        self.read_slot = BoundedSemaphore(1)

    def start(self):
        if self.thread is not None:
            return
        self.thread = Thread(target=self._recover, daemon=True, name='nico-review-pdf')
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=7)

    def _recover(self):
        cursor = ""
        while not self.stop.is_set():
            try:
                with self.jobs.adapter._connect() as con:
                    rows = con.execute(
                        "SELECT job_id,payload->'identity' AS identity FROM client_jobs "
                        "WHERE payload->>'workflow'=%s AND status IN ('queued','rendering') "
                        "AND CASE WHEN jsonb_typeof(payload->'lease_until_epoch')='number' "
                        "THEN (payload->>'lease_until_epoch')::numeric ELSE 0 END "
                        '<= EXTRACT(EPOCH FROM clock_timestamp()) AND job_id>%s ORDER BY job_id LIMIT 16',
                        (WORKFLOW, cursor),
                    ).fetchall()
                for row in rows:
                    if self.stop.is_set():
                        break
                    cursor = row['job_id']
                    try:
                        identity = PreparationIdentity(**row['identity'])
                        self._check_scope(identity)
                        self.source.check_policy(identity)
                        self.service.run_once(identity, stop=self.stop)
                    except Exception:
                        continue  # One invalid/failed job cannot starve later identities.
                if len(rows) < 16:
                    cursor = ''
            except Exception:
                # A storage outage never enables a memory/local fallback or a new job.
                pass
            self.stop.wait(5)

    def _check_scope(self, identity):
        if self.canary_scope is not None:
            self.canary_scope.check(identity)

    def _check_request_scope(self, run_id, language, binding):
        if self.canary_scope is not None:
            self.canary_scope.request(run_id, language, binding)

    def _bounded(self, seconds, operation, *, slot=None, observe=False, trace_id=None):
        slot = self.service.capacity if slot is None else slot
        if not slot.acquire(blocking=False):
            raise PreparationBusy('review_pdf_capacity_busy')
        guard = DeadlineGuard(seconds, self.stop)
        try:
            with AdmissionTrace(guard, trace_id).scope() if observe else nullcontext():
                return operation(guard)
        finally:
            guard.stop.set()
            def release():
                while not guard.idle():
                    Event().wait(.02)
                slot.release()
            if guard.idle():
                release()
            else:
                Thread(target=release, daemon=True, name='nico-review-request-quarantine').start()

    def prepare(self, run_id, language, binding, *, trace_id=None):
        # Full admission validation is retained. It must finish before the
        # browser's 30-second POST limit; a late restoration cannot enqueue.
        return self._bounded(20, lambda guard: self._prepare(run_id, language, binding, guard), observe=True, trace_id=trace_id)

    def qualify(self, run_id, language, binding):
        return self._bounded(20, lambda guard: self._prepare(run_id, language, binding, guard, qualify_only=True))

    def _prepare(self, run_id, language, binding, guard, *, qualify_only=False):
        self._check_request_scope(run_id, language, binding)
        with phase("policy"):
            renderer, policy = self.source.policy()
        def consume(row, restore):
            if row[1] is None or row[2] is None:
                raise PreparationConflict('review_commitment_required')
            record = restore()
            with phase("report_projection"):
                status = self.source.controller._status_artifact_from_record(record)
            with phase("lifecycle_binding"):
                reports = status.get('reports') or {}
                from nico.comprehensive_same_run_locale_report_v1 import _source_lifecycle_projection
                lifecycle = _source_lifecycle_projection(status, reports, reports.get('json') or {})
                if (record.get('terminal') is not True or lifecycle['approval_status'] != 'pending_human_approval'
                        or lifecycle['client_delivery_allowed'] is not False):
                    raise PreparationConflict('pending_review_draft_required')
                ident = record['identity']
                identity = PreparationIdentity(ident['customer_id'], ident['project_id'], run_id,
                    ident['repository'], ident['commit_sha'], record['revision'], record['integrity_sha256'],
                    reports['canonical_truth_sha256'], reports['pdf_sha256'], renderer, policy, language,
                    artifact_mode(status, language))
                self._binding(identity, binding)
                self._check_scope(identity)
                return identity
        identity = guard.call(self.source.store._consume_read_snapshot, run_id, consume)
        if qualify_only:
            return self.projection(dict(identity=asdict(identity), job_id=identity.job_id, status='eligible'))
        with phase("enqueue"):
            job = guard.call(self.jobs.enqueue, identity, preparation_authorized=True, check=guard.check, commit_guard=guard, timeout=5)
        return self.projection(job)

    @staticmethod
    def _binding(identity, binding):
        if binding != {'commit_sha': identity.commit_sha, 'canonical_truth_sha256': identity.canonical_truth_sha256}:
            raise PreparationConflict('review_pdf_binding_changed')

    def _job(self, run_id, language, job_id, binding, *, include_pdf=False):
        self._check_request_scope(run_id, language, binding)
        if not _JOB.fullmatch(job_id):
            raise PreparationConflict('review_pdf_job_invalid')
        with self.jobs.adapter._connect() as con:
            # Status never transfers the retained PDF blob or raw source report.
            expression = 'jobs.payload' if include_pdf else "jobs.payload - 'pdf_base64'"
            row = con.execute(
                f'SELECT {expression} AS payload, runs.customer_id, runs.project_id, '
                'runs.repository, runs.commit_sha, runs.revision, runs.integrity_sha256 '
                'FROM client_jobs AS jobs JOIN nico_comprehensive_runs AS runs ON runs.run_id=%s '
                "WHERE jobs.job_id=%s AND jobs.payload->>'workflow'=%s",
                (run_id, job_id, WORKFLOW),
            ).fetchone()
        if row is None:
            raise KeyError('review_pdf_job_unavailable')
        job = row['payload']
        identity = PreparationIdentity(**job['identity'])
        self._check_scope(identity)
        if identity.job_id != job_id or job['job_id'] != job_id or identity.run_id != run_id or identity.language != language:
            raise PreparationConflict('review_pdf_job_scope_changed')
        for name, expected in dict(customer_id=identity.customer_id, project_id=identity.project_id,
                repository=identity.repository, commit_sha=identity.commit_sha,
                revision=identity.source_revision, integrity_sha256=identity.source_integrity_sha256).items():
            if row[name] != expected:
                raise PreparationConflict('review_pdf_source_changed')
        self._binding(identity, binding)
        self.source.check_policy(identity)
        return identity, job

    @staticmethod
    def projection(job):
        state = {'rendering': 'verifying' if job.get('phase') == 'verifying' else 'preparing', 'rendered_unverified': 'verifying',
                 'failed': 'failed', 'budget_exhausted': 'failed', 'cancelled': 'cancelled'}.get(job['status'], job['status'])
        return dict(job_id=job['job_id'], state=state, run_id=job['identity']['run_id'],
            report_language=job['identity']['language'], commit_sha=job['identity']['commit_sha'],
            canonical_truth_sha256=job['identity']['canonical_truth_sha256'],
            artifact_mode=job['identity']['artifact_mode'],
            human_review_required=True, client_delivery_allowed=False,
            physical_worker_exit_confirmed=None)

    def lookup(self, run_id, language, binding):
        # Recover a committed idempotent admission whose response was lost.
        # No restore, enqueue, assessment or report body read on this GET.
        self._check_request_scope(run_id, language, binding)
        def read():
            renderer, policy = self.source.policy()
            with self.jobs.adapter._connect() as con:
                rows = con.execute(
                    "SELECT jobs.job_id FROM client_jobs jobs JOIN nico_comprehensive_runs runs "
                    "ON runs.run_id=jobs.payload->'identity'->>'run_id' "
                    "AND runs.revision::text=jobs.payload->'identity'->>'source_revision' "
                    "AND runs.integrity_sha256=jobs.payload->'identity'->>'source_integrity_sha256' "
                    "WHERE jobs.payload->>'workflow'=%s "
                    "AND jobs.payload->'identity'->>'run_id'=%s "
                    "AND jobs.payload->'identity'->>'language'=%s "
                    "AND jobs.payload->'identity'->>'commit_sha'=%s "
                    "AND jobs.payload->'identity'->>'canonical_truth_sha256'=%s "
                    "AND jobs.payload->'identity'->>'renderer_revision'=%s "
                    "AND jobs.payload->'identity'->>'policy_sha256'=%s "
                    "ORDER BY jobs.created_at DESC LIMIT 2",
                    (WORKFLOW, run_id, language, binding['commit_sha'], binding['canonical_truth_sha256'], renderer, policy),
                ).fetchall()
            for row in rows:
                try:
                    return self.projection(self._job(run_id, language, row['job_id'], binding)[1])
                except PreparationConflict:
                    continue
            raise KeyError('review_pdf_job_unavailable')
        return self._bounded(5, lambda guard: guard.call(read, timeout=5), slot=self.read_slot)

    def status(self, run_id, language, job_id, binding):
        return self._bounded(5, lambda guard: self.projection(guard.call(
            self._job, run_id, language, job_id, binding, timeout=5)[1]), slot=self.read_slot)

    def cancel(self, run_id, language, job_id, binding):
        # Cancellation cannot wait indefinitely behind a slow storage operation.
        # A late/uncertain commit remains fenced and is recovered by exact status.
        def operation(guard):
            identity, _ = guard.call(self._job, run_id, language, job_id, binding, timeout=5)
            def write():
                with self.jobs._transaction(identity, commit_guard=guard) as con:
                    job = self.jobs._read(con, identity)
                    guard.check()
                    if job['status'] in {'queued', 'rendering', 'rendered_unverified'}:
                        job.update(status='cancelled', lease_id='', lease_until_epoch=0,
                                   updated_epoch=self.jobs._now(con))
                        self.jobs._write(con, identity, job)
                return self.projection(job)
            return guard.call(write, timeout=5)
        return self._bounded(5, operation, slot=self.read_slot)

    def retrieve(self, run_id, language, job_id, binding):
        return self._bounded(230, lambda guard: guard.call(self._retrieve, run_id, language, job_id, binding))

    def _retrieve(self, run_id, language, job_id, binding):
        identity, _ = self._job(run_id, language, job_id, binding)
        captured = self.source.capture(identity)
        with self.jobs._transaction(identity) as con:
            self.source.lock_and_recheck(con, identity, postgres=True, storage_sha256=captured.storage_sha256)
            job = self.jobs._read(con, identity)
            if (job['status'] != 'ready' or job.get('source_snapshot_sha256') != _fingerprint(captured.status)
                    or job.get('source_storage_sha256') != captured.storage_sha256):
                raise PreparationConflict('review_pdf_not_verified_ready')
            result = dict(pdf_base64=job['pdf_base64'], identity=asdict(identity),
                          headers=job['result_headers'], validated_page_count=job['validated_page_count'])
            pdf, digest = validate_result(result, identity, parse_pdf=False)
            if digest != job['pdf_sha256'] or not job.get('result_owner'):
                raise PreparationConflict('review_pdf_retained_checksum_invalid')
        headers = {key: value for key, value in result['headers'].items()
                   if key.startswith('x-nico-') or key == 'content-disposition'}
        return Response(pdf, media_type='application/pdf', headers={**headers, **_HEADERS})


def _configured_runtime(app):
    if (os.getenv('NICO_ENABLE_REVIEW_PDF_PREPARATION') != 'true'
            or os.getenv('NICO_REVIEW_PDF_PG_QUALIFIED') != 'true'):
        return None
    canary_scope = CanaryScope.parse(os.getenv('NICO_REVIEW_PDF_CANARY_SCOPE', ''))
    controller = getattr(app.state, 'comprehensive_api_controller', None)
    store = controller._service._store if controller is not None else None
    state = getattr(app.state, 'comprehensive_runtime', {})
    if (store is None or store._dialect != 'postgres' or state.get('persistence_adapter') != 'postgres'
            or state.get('survives_container_replacement_verified') is not True):
        raise RuntimeError('review_pdf_verified_postgres_required')
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from nico.storage import PostgresAdapter
    from nico.comprehensive_final_report_background_v1 import _PUBLICATION_SLOT
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    # Reuse the canonical store's actual factory: no independent URL or schema init.
    def connect():
        con = store._connection_factory()
        con.row_factory = dict_row
        return con
    adapter._connect, adapter._jsonb = connect, Jsonb
    with connect() as con:
        con.execute('SELECT job_id,payload,status FROM client_jobs LIMIT 0')
        con.execute('SELECT run_id,payload FROM nico_comprehensive_runs LIMIT 0')
        con.execute('SELECT run_id,event_count,chain_sha256 FROM nico_comprehensive_review_history_commitments LIMIT 0')
    runtime_policy()
    source = RetainedSourceAuthority(store, controller, runtime_policy)
    return PreparationRuntime(ReviewPdfPreparationService(PostgresReviewPdfPreparationJobs(adapter),
                                                         source, capacity=_PUBLICATION_SLOT), canary_scope=canary_scope)


def install_review_pdf_preparation_api(app):
    if getattr(app.state, 'review_pdf_routes_installed', False):
        return
    app.state.review_pdf_routes_installed = True
    app.state.review_pdf_runtime = None
    def startup():
        runtime = None
        try:
            runtime = _configured_runtime(app)
            app.state.review_pdf_runtime = runtime
            if runtime is not None:
                runtime.start()
        except Exception:
            app.state.review_pdf_runtime = None  # Fail closed; never provision/fallback.
            if runtime is not None:
                runtime.close()
    def shutdown():
        runtime = app.state.review_pdf_runtime
        if runtime is not None:
            runtime.close()
    original_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(target):
        async with original_lifespan(target) as lifespan_state:
            await run_in_threadpool(startup)
            try:
                yield lifespan_state
            finally:
                await run_in_threadpool(shutdown)
    app.router.lifespan_context = lifespan

    async def endpoint(run_id: str, language: str, request: Request):
        authority = getattr(request.state, 'nico_specialist_authority', None)
        if not authority or authority.get('scope') == 'nico_production_proof':
            raise HTTPException(403, 'specialist_review_authority_required')
        # Same existing operator/session authorizer as review and edition routes.
        from nico.comprehensive_api_routes import _authorize_review
        _authorize_review(request.headers.get('x-nico-admin-token', ''))
        if not _RUN.fullmatch(run_id) or language not in {'en', 'es-MX'}:
            raise HTTPException(422, 'review_pdf_request_invalid')
        if request.method == 'GET' and request.query_params.get('storage_compatibility') is not None:
            if (request.url.path.endswith(('/pdf', '/cancel'))
                    or list(request.query_params.multi_items()) != [('storage_compatibility', 'true')]):
                raise HTTPException(422, 'review_pdf_diagnostic_request_invalid')
            from nico.review_pdf_storage_diagnostic_v1 import diagnose_storage
            return JSONResponse(await run_in_threadpool(diagnose_storage, app), headers=_HEADERS)
        if request.method == 'GET' and request.query_params.get('retained_binding') is not None:
            if (request.url.path.endswith(('/pdf', '/cancel'))
                    or list(request.query_params.multi_items()) != [('retained_binding', 'true')]):
                raise HTTPException(422, 'review_pdf_binding_request_invalid')
            from nico.review_pdf_retained_binding_v1 import retained_binding
            return JSONResponse(await run_in_threadpool(retained_binding, app, run_id, language), headers=_HEADERS)
        if request.method == 'GET' and request.query_params.get('canary_ledger') is not None:
            if (request.url.path.endswith(('/pdf', '/cancel'))
                    or list(request.query_params.multi_items()) != [('canary_ledger', 'true')]):
                raise HTTPException(422, 'review_pdf_ledger_request_invalid')
            from nico.review_pdf_ledger_diagnostic_v1 import diagnose_ledger
            return JSONResponse(await run_in_threadpool(diagnose_ledger, app, run_id, language), headers=_HEADERS)
        runtime = app.state.review_pdf_runtime
        if runtime is None:
            raise HTTPException(503, 'review_pdf_preparation_unavailable')
        response_headers = dict(_HEADERS)
        try:
            is_pdf = request.url.path.endswith('/pdf')
            is_cancel = request.url.path.endswith('/cancel')
            if request.method == 'POST':
                raw = await request.body()
                if len(raw) > 2048:
                    raise ValueError('request_too_large')
                payload = json.loads(raw)
                required = {'job_id', 'commit_sha', 'canonical_truth_sha256'} if is_cancel else {'prepare', 'commit_sha', 'canonical_truth_sha256'}
                if not isinstance(payload, dict) or set(payload) != required or request.query_params:
                    raise ValueError('invalid_request')
                binding = {k: payload[k] for k in ('commit_sha', 'canonical_truth_sha256')}
                if is_cancel:
                    result = await run_in_threadpool(runtime.cancel, run_id, language, payload['job_id'], binding)
                else:
                    if payload['prepare'] is not True:
                        raise ValueError('explicit_preparation_required')
                    trace_id = uuid4().hex
                    response_headers["X-NICO-Admission-Trace"] = trace_id
                    result = await run_in_threadpool(runtime.prepare, run_id, language, binding, trace_id=trace_id)
                return JSONResponse(result, status_code=200 if is_cancel else 202, headers=response_headers)
            params = dict(request.query_params)
            if not is_pdf and set(params) == {'qualify', 'commit_sha', 'canonical_truth_sha256'}:
                if params.pop('qualify') != 'true':
                    raise ValueError('invalid_qualification')
                return JSONResponse(await run_in_threadpool(runtime.qualify, run_id, language, params), headers=_HEADERS)
            if not is_pdf and set(params) == {'commit_sha', 'canonical_truth_sha256'}:
                return JSONResponse(await run_in_threadpool(runtime.lookup, run_id, language, params), headers=_HEADERS)
            if set(params) != {'job_id', 'commit_sha', 'canonical_truth_sha256'}:
                raise ValueError('invalid_query')
            job_id = params.pop('job_id')
            if is_pdf:
                return await run_in_threadpool(runtime.retrieve, run_id, language, job_id, params)
            return JSONResponse(await run_in_threadpool(runtime.status, run_id, language, job_id, params), headers=_HEADERS)
        except KeyError:
            raise HTTPException(404, 'review_pdf_unavailable', headers=response_headers) from None
        except PreparationConflict:
            raise HTTPException(409, 'review_pdf_binding_or_state_changed', headers=response_headers) from None
        except CommitOutcomeUnknown:
            raise HTTPException(503, 'review_pdf_commit_outcome_unknown', headers=response_headers) from None
        except RuntimeError:
            raise HTTPException(503, 'review_pdf_operation_unavailable_or_timed_out', headers=response_headers) from None
        except (ValueError, TypeError):
            raise HTTPException(422, 'review_pdf_request_or_artifact_invalid', headers=response_headers) from None
    app.add_api_route(ROUTE, endpoint, methods=['GET', 'POST'])
    app.add_api_route(ROUTE + '/pdf', endpoint, methods=['GET'])
    app.add_api_route(ROUTE + '/cancel', endpoint, methods=['POST'])
