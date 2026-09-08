"""Explicit owner recovery of the private GitHub checkout defect, once per scan.

No scanner output, review decision, or report can be replaced by this operation.
The prior checkout failure is preserved inside the same durable scanner record.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import re
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nico.comprehensive_scanner_inventory_v1 import _error, _mapping, _RUN, _COMMIT, _HEADERS
from nico.comprehensive_run_store import ComprehensiveRunNotFound
from nico.scanner_recovery import atomic_scanner_transition
from nico.specialist_access_v1 import SPECIALIST_SCOPE
from nico.storage import STORE

ROUTE = '/assessment/comprehensive-run/{run_id}/scanner-checkout-recovery'
MARKER = 'private_checkout_recovery_v1'
STAGE = 'dependency_security_static_analysis'


def _bound_failure(request, run_id):
    record = request.app.state.comprehensive_api_controller._service.load_read_only(run_id)
    identity = _mapping(record.get('identity'))
    stages = _mapping(record.get('stage_results'))
    stage = _mapping(stages.get(STAGE))
    snapshot = _mapping(_mapping(stages.get('immutable_repository_snapshot')).get('snapshot'))
    scan_id = stage.get('scan_id')
    if (identity.get('run_id') != run_id or not _COMMIT.fullmatch(str(identity.get('commit_sha') or ''))
            or not isinstance(scan_id, str) or not scan_id.startswith('scan_snapshot_')):
        raise ValueError('checkout_recovery_identity_unavailable')
    # Read the durable record, not a stale process cache.
    scan = STORE.get('scanner_runs', scan_id)
    if not isinstance(scan, Mapping) or scan.get('scan_id') != scan_id or any(
        not identity.get(key) or scan.get(key) != identity[key]
        for key in ('run_id', 'customer_id', 'project_id', 'repository')
    ) or scan.get('snapshot_commit_sha') != identity['commit_sha']:
        raise ValueError('checkout_recovery_identity_mismatch')
    if (snapshot.get('commit_sha') != identity['commit_sha']
            or snapshot.get('snapshot_id') != scan.get('snapshot_id')
            or snapshot.get('repository') != identity['repository']
            or snapshot.get('access_mode', snapshot.get('provider_access_mode')) != 'authenticated_read_only'
            or snapshot.get('credential_used', snapshot.get('provider_credential_used')) is not True
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', identity['repository'])):
        raise ValueError('checkout_recovery_private_snapshot_required')
    notes = scan.get('unavailable_data_notes')
    known_failure = isinstance(notes, list) and any(
        isinstance(note, str) and (note.startswith('Exact snapshot ancestry fetch failed:')
                                  or note == 'github_authenticated_snapshot_fetch_failed') for note in notes)
    eligible = (record.get('status') == 'blocked' and record.get('current_stage') == STAGE
                and stage.get('reason') == 'snapshot_scanner_not_verified'
                and scan.get('status') == 'unavailable'
                and scan.get('current_stage') == 'snapshot_verification_failed'
                and scan.get('actual_commit_sha') == '' and scan.get('snapshot_match') is False
                and scan.get('scanner_results') == [] and scan.get('tools_run') == []
                and known_failure and MARKER not in scan
                and bool(scan.get('authorized_by')) and bool(scan.get('authorization_scope'))
                and isinstance(scan.get('tools_requested'), list) and bool(scan['tools_requested']))
    fingerprint = hashlib.sha256(json.dumps(scan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    summary = {'run_id': run_id, 'scan_id': scan_id, 'commit_sha': identity['commit_sha'],
               'retry_allowed': eligible, 'failure_fingerprint': fingerprint,
               'reason': 'private_snapshot_checkout_failed' if eligible else 'checkout_retry_not_eligible',
               'scanner_completion_verified': False, 'client_delivery_allowed': False}
    return scan, summary


def _operate(request, run_id, payload=None):
    try:
        scan, summary = _bound_failure(request, run_id)
        if payload is None:
            return JSONResponse({**summary, 'read_only': True}, headers=_HEADERS)
        if (not isinstance(payload, dict) or set(payload) != {'scan_id', 'commit_sha', 'failure_fingerprint'}
                or any(payload[key] != summary[key] for key in payload)
                or not summary['retry_allowed']):
            return _error(409, 'checkout_retry_not_eligible_or_stale')
        from nico import scanner_worker, snapshot_scanner_worker
        scan_id = summary['scan_id']
        retained = {'previous_failure': deepcopy(scan), 'failure_fingerprint': summary['failure_fingerprint'],
                    'requested_at': scanner_worker.now_iso(), 'actor': 'authenticated_nico_owner',
                    'automatic_retry': False, 'attempt': 1}
        claimed = atomic_scanner_transition(scan_id, {'unavailable'}, 'queued', {
            MARKER: retained, 'current_stage': 'queued', 'completed_at': None, 'progress_percent': 2,
            'provider_access_mode': 'authenticated_read_only', 'provider_credential_used': True,
        }, store=STORE, require_absent_field=MARKER)
        if claimed is None:
            return _error(409, 'checkout_retry_already_claimed')
        scanner_worker.SCAN_JOBS[scan_id] = deepcopy(claimed)
        work = {key: claimed[key] for key in ('run_id', 'repository', 'customer_id', 'project_id',
                'snapshot_id', 'snapshot_commit_sha', 'authorized_by', 'authorization_scope',
                'provider_access_mode', 'provider_credential_used')}
        work.update(authorized=True, tools=list(claimed['tools_requested']))
        try:
            STORE.audit('scanner.private_checkout_retry', {key: summary[key] for key in ('run_id', 'scan_id', 'commit_sha', 'failure_fingerprint')},
                        customer_id=claimed['customer_id'], project_id=claimed['project_id'])
            threading.Thread(target=snapshot_scanner_worker._run_snapshot_scan,
                             args=(scan_id, work), daemon=True).start()
        except Exception:
            failed = atomic_scanner_transition(scan_id, {'queued'}, 'unavailable', {
                'current_stage': 'snapshot_verification_failed',
                'unavailable_data_notes': ['checkout_retry_worker_start_failed'],
            }, store=STORE)
            if failed:
                scanner_worker.SCAN_JOBS[scan_id] = deepcopy(failed)
            return _error(503, 'checkout_retry_worker_start_failed')
        return JSONResponse({**summary, 'retry_allowed': False, 'status': 'queued',
                             'same_run_and_scan_preserved': True, 'prior_failure_retained': True},
                            status_code=202, headers=_HEADERS)
    except ComprehensiveRunNotFound:
        return _error(404, 'checkout_recovery_unavailable')
    except ValueError:
        return _error(409, 'checkout_recovery_unavailable')
    except Exception:
        return _error(503, 'checkout_recovery_unavailable')


def install_scanner_checkout_recovery(app: FastAPI):
    if getattr(app.state, MARKER, False):
        return

    async def endpoint(run_id: str, request: Request):
        authority = _mapping(getattr(request.state, 'nico_specialist_authority', None))
        if authority.get('authority') != 'nico_admin' or authority.get('scope') not in {
            SPECIALIST_SCOPE, 'comprehensive_review_and_delivery',
        }:
            return _error(403, 'owner_administration_required')
        if not _RUN.fullmatch(run_id) or request.query_params:
            return _error(422, 'checkout_recovery_request_invalid')
        payload = None
        if request.method == 'POST':
            try:
                payload = await request.json()
            except Exception:
                return _error(422, 'checkout_recovery_request_invalid')
            if payload is None:
                return _error(422, 'checkout_recovery_request_invalid')
        return await run_in_threadpool(_operate, request, run_id, payload)

    app.add_api_route(ROUTE, endpoint, methods=['GET', 'POST'], tags=['assessment'])
    app.state.private_checkout_recovery_v1 = True
    app.openapi_schema = None
