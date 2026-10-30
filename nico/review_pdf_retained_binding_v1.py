"""Bounded operator metadata read. Never admits work or maintains retained records."""
import json
from threading import BoundedSemaphore, Event, Thread

from nico.review_pdf_canary_scope_v1 import CanaryScope
from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard

_SLOT = BoundedSemaphore(1)
DEADLINE_SECONDS = 20
MAX_RESPONSE_BYTES = 20 * 1024
SCHEMA = 'nico.pdf-retained-binding.v1'


def unavailable(status='unavailable'):
    return dict(schema=SCHEMA, status=status, binding=None, snapshot_validated=False,
                lifecycle_qualified=False, activation_authorized=False)


def inspect_binding(app, run_id, language, guard):
    controller = app.state.comprehensive_api_controller
    store = controller._service._store
    guard.check()
    # This reader rejects absent commitments; unlike load/status it cannot create
    # legacy commitments, reconcile intake, continue a run or refresh projections.
    record = store.load_without_maintenance(run_id)
    guard.check()
    if (type(record) is not dict or record.get('terminal') is not True
            or record.get('identity', {}).get('run_id') != run_id):
        raise ValueError('invalid_retained_binding')
    # The same validated package boundary used by actual preparation admission.
    # This is an in-memory projection, not controller.status()/continuation.
    status = controller._status_artifact_from_record(record)
    guard.check()
    from nico.comprehensive_same_run_locale_report_v1 import _source_lifecycle_projection
    reports = status.get('reports') or {}
    lifecycle = _source_lifecycle_projection(status, reports, reports.get('json') or {})
    if (status.get('terminal') is not True or record.get('status') in {'approved', 'rejected', 'declined'}
            or lifecycle['approval_status'] != 'pending_human_approval'
            or lifecycle['client_delivery_allowed'] is not False):
        raise ValueError('invalid_retained_binding')
    identity = record['identity']
    for field in ('run_id', 'customer_id', 'project_id', 'repository', 'commit_sha'):
        if status.get(field) != identity.get(field):
            raise ValueError('invalid_retained_binding')
    if (status.get('revision') != record['revision']
            or status.get('integrity_sha256') != record['integrity_sha256']):
        raise ValueError('invalid_retained_binding')
    binding = {field: identity[field] for field in
               ('run_id', 'customer_id', 'project_id', 'repository', 'commit_sha')}
    binding.update(source_revision=record['revision'],
                   source_integrity_sha256=record['integrity_sha256'],
                   canonical_truth_sha256=reports['canonical_truth_sha256'],
                   source_artifact_sha256=reports['pdf_sha256'], language=language)
    CanaryScope.parse(json.dumps(binding, ensure_ascii=False))
    result = dict(schema=SCHEMA, status='available', binding=binding,
                  source_report_language=status['report_language'],
                  snapshot_validated=True, terminal=True,
                  human_review_required=True, client_delivery_allowed=False,
                  lifecycle_qualified=False, activation_authorized=False)
    if (status['report_language'] not in {'en', 'es-MX'}
            or len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_RESPONSE_BYTES):
        raise ValueError('invalid_retained_binding')
    guard.check()
    return result


def retained_binding(app, run_id, language):
    if not _SLOT.acquire(blocking=False):
        return unavailable('busy')
    # Share existing heavy-publication capacity. This read cannot overlap a
    # preparation worker/admission in the same process, nor create another pool.
    from nico.comprehensive_final_report_background_v1 import _PUBLICATION_SLOT
    if not _PUBLICATION_SLOT.acquire(blocking=False):
        _SLOT.release()
        return unavailable('busy')
    guard = DeadlineGuard(DEADLINE_SECONDS, Event())
    try:
        return guard.call(inspect_binding, app, run_id, language, guard)
    except Exception:
        # No raw error, report body, source text, credential or partial binding.
        return unavailable()
    finally:
        guard.stop.set()
        def release():
            while not guard.idle():
                Event().wait(.02)
            _PUBLICATION_SLOT.release()
            _SLOT.release()
        if guard.idle():
            release()
        else:
            Thread(target=release, daemon=True, name='nico-binding-read-quarantine').start()
