"""Add a separately owned C++ child without replacing ordinary scanner rows.

Only internal qualified selection may call enqueue_cpp_child. Public payload
fields cannot select a contract, image or command. Composition never writes
either source row and never changes the child's retained artifact binding.
"""
from copy import deepcopy
from dataclasses import asdict

from nico.assessment_worker_jobs import JobConflict, JobIdentity, JobLimits, WorkerJobs, _digest

_CONTEXT = ('customer_id', 'project_id', 'run_id', 'repository', 'snapshot_commit_sha',
            'snapshot_id', 'provider_access_mode', 'provider_credential_used')
_TOTALS = ('raw_total', 'material_total', 'review_required_total',
           'approved_or_nonblocking_total', 'excluded_test_only_total')


def parent_scan_id(parent, contract_sha, release):
    return 'scan_snapshot_cpp_' + _digest({key: parent.get(key) for key in _CONTEXT}
        | {'tools_requested': sorted(parent['tools_requested']),
           'contract_sha256': contract_sha, 'release_revision': release})[:40]


def child_binding(parent, identity):
    return {'schema': 'nico.cpp-scan-child.v1', 'parent_scan_id': parent['scan_id'],
            'worker_job_id': identity.job_id, 'identity': asdict(identity)}


def _identity(parent, child, job):
    try:
        binding = parent['cpp_worker_child']
        identity = JobIdentity(**binding['identity'])
        expected = {'scan_id': identity.scan_id, 'worker_job_id': identity.job_id,
            'parent_scan_id': parent['scan_id'], **{key: parent.get(key) for key in _CONTEXT}}
        scope = {'customer_id': identity.customer_id, 'project_id': identity.project_id,
            'run_id': identity.run_id, 'repository': identity.repository_id,
            'snapshot_commit_sha': identity.revision}
        if (binding != child_binding(parent, identity) or identity.scan_id == parent['scan_id']
                or parent['scan_id'] != parent_scan_id(parent, identity.contract_sha256, identity.release_revision)
                or any(parent.get(key) != value for key, value in scope.items())
                or any(child.get(key) != value for key, value in expected.items())
                or child.get('tools_requested') != ['cppcheck'] or 'cpp_worker_child' in child
                or job.get('job_id') != identity.job_id or job.get('identity') != asdict(identity)
                or _digest(job.get('contract')) != identity.contract_sha256):
            raise ValueError('binding')
        return identity
    except (KeyError, TypeError, ValueError, AttributeError):
        raise JobConflict('cpp_child_binding_mismatch') from None


def compose_cpp_scan(parent, child, job):
    identity = _identity(parent, child, job)
    result = deepcopy(parent)
    records = deepcopy(child.get('scanner_results') or [])
    if child.get('status') == 'complete' and (not records or job.get('status') != 'completed'
            or child.get('snapshot_match') is not True or child.get('actual_commit_sha') != identity.revision):
        raise JobConflict('cpp_child_completion_unverified')
    for record in records:
        if ((record.get('tool') or record.get('scanner_name')) != 'cppcheck'
                or any(record.get(key) != value for key, value in {
                    'scan_id': identity.scan_id, 'run_id': identity.run_id,
                    'customer_id': identity.customer_id, 'project_id': identity.project_id,
                    'repository': identity.repository_id, 'commit_sha': identity.revision}.items())):
            raise JobConflict('cpp_child_record_binding_mismatch')
    parent_status, child_status = parent.get('status'), child.get('status')
    result.update(ordinary_scan_status=parent_status, cpp_worker_status=child_status)
    terminal_failure = child_status not in {'queued', 'running', 'complete'}
    if terminal_failure and not records:
        records = [{'tool': 'cppcheck', 'scanner_name': 'cppcheck', 'scan_id': identity.scan_id,
            'run_id': identity.run_id, 'customer_id': identity.customer_id,
            'project_id': identity.project_id, 'repository': identity.repository_id,
            'commit_sha': identity.revision, 'status': 'failed', 'execution_state': 'failed',
            'applicability_state': 'unproven', 'completed': False, 'verified_complete': False,
            'verified_for_this_report': False, 'findings': [], 'raw_artifact_retention_complete': False,
            'reason': 'The dedicated C++ child ended without a retained native receipt.',
            'worker_failure_code': child.get('worker_failure_code') or child_status,
            'human_review_required': True, 'client_delivery_allowed': False}]
    result['scanner_results'] = [*result.get('scanner_results', []), *records]
    for name in ('tools_requested', 'tools_run', 'failed_tools', 'timed_out_tools', 'unavailable_tools'):
        result[name] = sorted(set(parent.get(name) or []) | set(child.get(name) or []))
    if terminal_failure:
        result['failed_tools'] = sorted(set(result['failed_tools']) | {'cppcheck'})
    if parent_status != 'cancelled' and child_status in {'queued', 'running'}:
        result.update(status='running', current_stage='ordinary_and_cpp_scanners', progress_percent=min(
            int(parent.get('progress_percent') or 0), int(child.get('progress_percent') or 0)))
    elif parent_status in {'queued', 'running'}:
        result['status'] = 'running'
    summary = deepcopy(parent.get('finding_summary') or {})
    child_summary = (child.get('finding_summary') or {}) if child_status == 'complete' else {}
    for key in _TOTALS:
        summary[key] = int(summary.get(key) or 0) + int(child_summary.get(key) or 0)
    by_tool = summary.setdefault('by_tool', {})
    if set(by_tool) & set(child_summary.get('by_tool') or {}):
        raise JobConflict('cpp_child_duplicate_tool_population')
    by_tool.update(deepcopy(child_summary.get('by_tool') or {}))
    by_category = summary.setdefault('by_category', {})
    for category, counts in (child_summary.get('by_category') or {}).items():
        target = by_category.setdefault(category, {})
        for name, value in counts.items():
            target[name] = int(target.get(name) or 0) + int(value)
    result['finding_summary'] = summary
    for field, total in {'finding_count': 'raw_total', 'material_finding_count': 'material_total',
            'review_required_finding_count': 'review_required_total',
            'excluded_test_only_finding_count': 'excluded_test_only_total'}.items():
        result[field] = summary[total]
    evidence = result.setdefault('evidence_summary', {})
    evidence.update(finding_summary=deepcopy(summary), cpp_worker_scan_id=identity.scan_id)
    for name in ('tools_requested', 'tools_run', 'failed_tools', 'timed_out_tools', 'unavailable_tools'):
        evidence[name] = len(result[name])
    return result


def read_cpp_composition(parent, store, read_scan):
    binding = parent.get('cpp_worker_child') or {}
    child_id = (binding.get('identity') or {}).get('scan_id')
    if not child_id or child_id == parent.get('scan_id'):
        raise JobConflict('cpp_child_binding_mismatch')
    child = store.get('scanner_runs', child_id)
    if not child or 'cpp_worker_child' in child:
        raise JobConflict('cpp_child_missing_or_nested')
    child = read_scan(child_id)  # applies existing durable lease/deadline polling
    job = WorkerJobs(store.adapter).get_by_id(binding.get('worker_job_id', ''))
    return compose_cpp_scan(parent, child, job)


def enqueue_cpp_child(parent, contract, adapter):
    """Atomically retain both rows and their link before one external dispatch."""
    from nico.assessment_worker_receipts import prepare_snapshot_scan, validate_contract
    from nico.github_actions_proof_auth_v1 import expected_release_sha
    from nico.assessment_worker_dispatch import dispatch_if_enabled
    contract = validate_contract(contract)
    parent = deepcopy(parent)
    if 'cppcheck' in parent['tools_requested'] or 'worker_job_id' in parent or 'cpp_worker_child' in parent:
        raise ValueError('cpp_child_requires_ordinary_parent')
    parent['scan_id'] = parent_scan_id(parent, _digest(contract), expected_release_sha())
    child = deepcopy(parent)
    child.update(parent_scan_id=parent['scan_id'], tools_requested=['cppcheck'])
    child, contract, identity = prepare_snapshot_scan(child, contract)
    parent['cpp_worker_child'] = child_binding(parent, identity)
    job = WorkerJobs(adapter).enqueue(identity, JobLimits(**contract['limits']),
        contract=contract, scan=child, parent_scan=parent)
    # Persisted one-attempt dispatch reservations retain existing ambiguous-
    # response behavior. Repeated intake does not reset deadlines or results.
    dispatch_if_enabled(adapter.get('scanner_runs', identity.scan_id), adapter)
    return adapter.get('scanner_runs', parent['scan_id']), job['parent_created']


def publish_cpp_parent(value, adapter):
    """Fence stale ordinary writes after recovery or operator close.

    The thread keeps its own starting recovery generation. It cannot adopt a
    newer generation from the shared cache and overwrite that generation.
    """
    with adapter._connect() as connection:
        row = connection.execute('SELECT payload FROM scanner_runs WHERE scan_id=%s FOR UPDATE',
                                 (value['scan_id'],)).fetchone()
        current = row['payload'] if row else None
        if not current or current.get('status') not in {'queued', 'running'}:
            return False
        if any(current.get(key) != value.get(key) for key in (
                *_CONTEXT, 'cpp_worker_child', 'tools_requested', 'recovery',
                'authorized_by', 'authorization_scope')):
            return False
        retained = deepcopy(value)
        # Liveness is independently patched while a tool runs. Preserve the
        # newer heartbeat without letting it replace this execution's fence.
        retained.update({key: data for key, data in current.items() if key.startswith('heartbeat_')
                         or key.startswith('tool_')})
        connection.execute('UPDATE scanner_runs SET status=%s,payload=%s,updated_at=clock_timestamp() '
            'WHERE scan_id=%s AND customer_id=%s AND project_id=%s',
            (value['status'], adapter._jsonb(retained), value['scan_id'], value['customer_id'], value['project_id']))
    return True


def close_cpp_parent(parent, adapter, expected_statuses, patch, require_absent_field=None):
    """Share the authorized parent close and child fence in one transaction."""
    binding = parent['cpp_worker_child']
    jobs = WorkerJobs(adapter)
    job = jobs.get_by_id(binding['worker_job_id'])
    child = adapter.get('scanner_runs', binding['identity']['scan_id'])
    identity = _identity(parent, child, job)
    closed = []
    def publish(connection, current_job):
        row = connection.execute('SELECT payload FROM scanner_runs WHERE scan_id=%s FOR UPDATE',
                                 (parent['scan_id'],)).fetchone()
        current = row['payload'] if row else None
        _identity(current, child, current_job)
        if (current['status'] not in expected_statuses
                or (require_absent_field is not None and require_absent_field in current)):
            raise JobConflict('cpp_parent_close_conflict')
        value = {**current, **deepcopy(patch), 'status': 'cancelled'}
        _identity(value, child, current_job)
        connection.execute('UPDATE scanner_runs SET status=%s,payload=%s,updated_at=clock_timestamp() '
            'WHERE scan_id=%s AND customer_id=%s AND project_id=%s',
            ('cancelled', adapter._jsonb(value), parent['scan_id'], identity.customer_id, identity.project_id))
        closed.append(value)
    jobs.cancel(identity, publish=publish)
    return closed[0]
