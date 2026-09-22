"""Synthetic additive scan transactions; no repository or analyzer executes."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from nico.assessment_worker_jobs import JobConflict, JobIdentity, WorkerJobs
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from nico.scanner_raw_artifact_storage_v1 import read_scanner_artifact
from nico import scanner_worker, snapshot_scanner_worker, scanner_recovery
from nico.assessment_required_tools import install_required_assessment_tools, REQUIRED_EXACT_SNAPSHOT_TOOLS
from nico.storage import STORE
from scripts.worker_protocol_fixture import contract, receipt


def prove_cpp_composition(adapter, post, worker):
    install_required_assessment_tools()
    jobs = WorkerJobs(adapter)
    checks = {}
    def enqueue():
        run = 'synthetic-cpp-composition-' + uuid4().hex
        payload = {'authorized': True, 'authorized_by': 'owned_synthetic_protocol_fixture',
            'authorization_scope': 'synthetic transactions only; no repository execution',
            'customer_id': run, 'project_id': 'synthetic-project', 'run_id': run,
            'repository': 'example/owned-control', 'snapshot_id': 'snapshot-owned',
            'snapshot_commit_sha': 'a' * 40, 'provider_access_mode': 'anonymous_public',
            'provider_credential_used': False, 'tools': ['bandit']}
        launched = []
        original = snapshot_scanner_worker.threading.Thread
        snapshot_scanner_worker.threading.Thread = lambda **kwargs: SimpleNamespace(start=lambda: launched.append(kwargs))
        try:
            first = snapshot_scanner_worker.start_snapshot_scan(payload, cpp_contract=contract())
            second = snapshot_scanner_worker.start_snapshot_scan(payload, cpp_contract=contract())
        finally:
            snapshot_scanner_worker.threading.Thread = original
        assert len(launched) == 1 and first['scan_id'] == second['scan_id']
        parent = adapter.get('scanner_runs', first['scan_id'])
        binding = parent['cpp_worker_child']
        identity = JobIdentity(**binding['identity'])
        child = adapter.get('scanner_runs', identity.scan_id)
        assert parent['tools_requested'] == list(REQUIRED_EXACT_SNAPSHOT_TOOLS)
        assert child['tools_requested'] == ['cppcheck']
        assert child['parent_scan_id'] == parent['scan_id'] and jobs.get(identity)['attempts'] == 0
        return parent, identity

    def ordinary_complete(parent):
        value = deepcopy(parent)
        value.update(status='complete', snapshot_match=True, actual_commit_sha='a' * 40,
            scanner_results=[{'tool': 'bandit', 'status': 'unavailable', 'findings': [],
                              'reason': 'Synthetic ordinary row; no scanner execution claimed.'}],
            unavailable_tools=['bandit'], current_stage='complete', progress_percent=100)
        adapter.put('scanner_runs', value['scan_id'], value)
        return value

    first, identity = enqueue()
    checks['cpp_child_link_and_duplicate_intake_are_durable'] = True
    claim = post(identity, 'claim', {})
    post(identity, 'receipt', {'lease_id': claim['lease_id'], 'receipt': receipt(identity, claim['lease_id'], worker)})
    assert scanner_worker.get_scan(first['scan_id'])['status'] == 'running'
    before_child = deepcopy(adapter.get('scanner_runs', identity.scan_id))
    retained_parent = ordinary_complete(first)
    joined = scanner_worker.get_scan(first['scan_id'])
    assert joined['status'] == 'complete' and joined['scanner_results'][0] == retained_parent['scanner_results'][0]
    assert adapter.get('scanner_runs', first['scan_id']) == retained_parent
    assert adapter.get('scanner_runs', identity.scan_id) == before_child
    checks['cpp_child_first_completion_does_not_overwrite_ordinary_results'] = True

    record = joined['scanner_results'][1]
    binding = {key: record[key] for key in ('run_id', 'scan_id', 'customer_id', 'project_id', 'repository', 'commit_sha', 'scanner_name')}
    raw = read_scanner_artifact(record, binding=binding)
    assert raw.metadata['availability'] == 'verified'
    compact = next(row for row in compact_scanner_records(joined, commit_sha=identity.revision) if row['tool'] == 'cppcheck')
    assert compact['scan_id'] == identity.scan_id and compact['evidence_reference'] == 'scanner_runs/' + identity.scan_id
    scanner_worker.SCAN_JOBS.pop(first['scan_id'], None)
    restarted = scanner_worker.get_scan(first['scan_id'])
    assert restarted == joined and read_scanner_artifact(restarted['scanner_results'][1], binding=binding).raw == raw.raw
    checks['cpp_composition_refresh_and_child_artifact_binding_survive_cache_loss'] = True

    second, identity2 = enqueue()
    ordinary_complete(second)
    assert scanner_worker.get_scan(second['scan_id'])['status'] == 'running'
    claim2 = post(identity2, 'claim', {})
    post(identity2, 'receipt', {'lease_id': claim2['lease_id'], 'receipt': receipt(identity2, claim2['lease_id'], worker)})
    assert scanner_worker.get_scan(second['scan_id'])['status'] == 'complete'
    checks['cpp_parent_first_completion_waits_for_child'] = True

    closing, cancelled = enqueue()
    owner = post(cancelled, 'claim', {})
    closing.update(status='recovery_required', recovery={'state': 'recovery_required'})
    adapter.put('scanner_runs', closing['scan_id'], closing)
    closed = scanner_recovery.close_interrupted_scanner_run(closing['scan_id'], actor='synthetic-operator',
        reason_code='no_longer_required', store=STORE)
    assert closed['status'] == 'cancelled' and jobs.get(cancelled)['status'] == 'cancelled'
    post(cancelled, 'receipt', {'lease_id': owner['lease_id'], 'receipt': receipt(cancelled, owner['lease_id'], worker)}, expected=409)
    assert scanner_worker.get_scan(closing['scan_id'])['status'] == 'cancelled'
    checks['cpp_authorized_parent_close_fences_late_child_receipt'] = True

    from nico.assessment_cpp_integration import close_cpp_parent
    untouched, pending = enqueue()
    before = deepcopy(jobs.get(pending))
    try:
        close_cpp_parent(untouched, adapter, {'recovery_required'}, {'human_review_required': True})
    except JobConflict:
        pass
    else:
        raise AssertionError('wrong-state close did not reject')
    assert jobs.get(pending) == before and adapter.get('scanner_runs', untouched['scan_id']) == untouched
    checks['cpp_parent_close_conflict_rolls_back_child_cancellation'] = True

    from nico.snapshot_scanner_resilience_patch import _terminalize_worker_failure, _resume_snapshot_scanner_run
    late, _ = enqueue()
    original_clone = snapshot_scanner_worker.clone_repository_at_snapshot
    def close_during_clone(*_args):
        assert scanner_recovery.atomic_scanner_transition(late['scan_id'], {'running'},
            'recovery_required', {'recovery': {'state': 'recovery_required'}}, store=STORE)
        assert scanner_recovery.close_interrupted_scanner_run(late['scan_id'], actor='synthetic-operator',
            reason_code='no_longer_required', store=STORE)['status'] == 'cancelled'
        return None, '', ['Synthetic operator close; no repository or tool execution.']
    snapshot_scanner_worker.clone_repository_at_snapshot = close_during_clone
    try:
        snapshot_scanner_worker._run_snapshot_scan(late['scan_id'], {'tools': ['bandit']}, execution_record=late)
    finally:
        snapshot_scanner_worker.clone_repository_at_snapshot = original_clone
    after_close = adapter.get('scanner_runs', late['scan_id'])
    assert after_close['status'] == 'cancelled' and after_close['recovery']['state'] == 'closed_by_operator'
    _terminalize_worker_failure(late['scan_id'], RuntimeError('synthetic late failure'), store=STORE,
                               execution_record=late)
    assert adapter.get('scanner_runs', late['scan_id']) == after_close
    checks['cpp_close_fences_ordinary_thread_and_failure_publication'] = True

    resumed, _ = enqueue()
    scanner_recovery.atomic_scanner_transition(resumed['scan_id'], {'queued'}, 'recovery_required',
        {'recovery': {'state': 'recovery_required'}}, store=STORE)
    launches = []
    result = _resume_snapshot_scanner_run(resumed['scan_id'], actor='synthetic-operator', store=STORE,
        thread_factory=lambda **kwargs: SimpleNamespace(start=lambda: launches.append(kwargs)))
    assert result['status'] == 'queued' and len(launches) == 1
    stale = {**deepcopy(resumed), 'status': 'complete'}
    assert snapshot_scanner_worker._persist_snapshot_scan(stale, STORE) is False
    new_generation = launches[0]['kwargs']['execution_record']
    assert new_generation['recovery']['attempt'] == 1
    new_generation['status'] = 'running'
    assert snapshot_scanner_worker._persist_snapshot_scan(new_generation, STORE) is True
    checks['cpp_resumed_ordinary_generation_rejects_stale_writers'] = True
    return checks
