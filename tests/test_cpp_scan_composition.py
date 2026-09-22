"""Additive worker evidence must preserve ordinary scanner and artifact identity."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from nico.assessment_worker_jobs import JobConflict
from nico.assessment_worker_receipts import validate_receipt
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from scripts.worker_protocol_fixture import contract, identity, receipt


def population(parent_status='complete', child_status='complete'):
    from nico.assessment_cpp_integration import parent_scan_id, child_binding
    plan = contract()
    parent = {'scan_id': 'pending', 'customer_id': 'synthetic-tenant', 'project_id': 'synthetic-project',
        'run_id': 'synthetic-run', 'repository': 'example/owned-control', 'snapshot_commit_sha': 'a' * 40,
        'snapshot_id': 'snapshot-owned', 'provider_access_mode': 'anonymous_public', 'provider_credential_used': False,
        'status': parent_status, 'tools_requested': ['bandit'], 'tools_run': ['bandit'] if parent_status == 'complete' else [],
        'actual_commit_sha': 'a' * 40, 'snapshot_match': parent_status == 'complete',
        'scanner_results': [{'tool': 'bandit', 'scanner_name': 'bandit', 'status': 'completed', 'findings': [],
                             'commit_sha': 'a' * 40, 'raw_artifact_sha256': 'f' * 64}],
        'finding_summary': {'raw_total': 0, 'material_total': 0, 'review_required_total': 0,
                            'by_tool': {'bandit': {'raw': 0, 'material': 0, 'review_required': 0}}}}
    job_identity = identity(plan)
    parent['scan_id'] = parent_scan_id(parent, job_identity.contract_sha256, job_identity.release_revision)
    parent['cpp_worker_child'] = child_binding(parent, job_identity)
    raw, record, _ = validate_receipt(job_identity, plan, 'e' * 32, 'github:123456:12345678:1', receipt())
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256='d' * 64)
    child = {**{k: parent[k] for k in ('customer_id', 'project_id', 'run_id', 'repository',
        'snapshot_id', 'snapshot_commit_sha', 'provider_access_mode', 'provider_credential_used')},
        'scan_id': job_identity.scan_id, 'worker_job_id': job_identity.job_id,
        'parent_scan_id': parent['scan_id'], 'status': child_status, 'tools_requested': ['cppcheck'],
        'tools_run': ['cppcheck'] if child_status == 'complete' else [], 'snapshot_match': child_status == 'complete',
        'actual_commit_sha': 'a' * 40, 'scanner_results': [record] if child_status == 'complete' else [],
        'finding_summary': {'raw_total': 1, 'material_total': 0, 'review_required_total': 1,
            'by_tool': {'cppcheck': {'raw': 1, 'material': 0, 'review_required': 1}}}}
    job = {'job_id': job_identity.job_id, 'identity': asdict(job_identity), 'contract': plan,
           'status': 'completed' if child_status == 'complete' else child_status}
    return parent, child, job


def test_composition_keeps_both_sources_without_mutating_retained_rows():
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population(); before = deepcopy((parent, child, job))
    result = compose_cpp_scan(parent, child, job)
    assert (parent, child, job) == before
    assert result['status'] == 'complete' and result['scan_id'] == parent['scan_id']
    assert result['tools_run'] == ['bandit', 'cppcheck']
    assert result['scanner_results'][0] == parent['scanner_results'][0]
    assert result['scanner_results'][1] == child['scanner_results'][0]
    assert result['finding_summary']['review_required_total'] == 1
    compact = compact_scanner_records(result, commit_sha='a' * 40)
    cpp = next(row for row in compact if row['tool'] == 'cppcheck')
    assert cpp['scan_id'] == child['scan_id'] and cpp['evidence_reference'] == 'scanner_runs/' + child['scan_id']
    assert cpp['raw_artifact_sha256'] == child['scanner_results'][0]['raw_artifact_sha256']


def test_composed_counts_reach_canonical_consumers_and_evidence_summary():
    from nico.assessment_cpp_integration import compose_cpp_scan
    from nico.comprehensive_native_providers import _counts
    parent, child, job = population()
    parent['finding_summary'].update(raw_total=4, material_total=1,
        review_required_total=2, excluded_test_only_total=1)
    parent.update(finding_count=4, material_finding_count=1,
        review_required_finding_count=2, excluded_test_only_finding_count=1,
        evidence_summary={'tools_requested': 1, 'tools_run': 1, 'repo_size_bytes': 17,
                          'finding_summary': deepcopy(parent['finding_summary'])})
    result = compose_cpp_scan(parent, child, job)
    assert _counts(result) == {'raw': 5, 'material': 1, 'review': 3, 'excluded': 1}
    assert result['evidence_summary']['finding_summary'] == result['finding_summary']
    assert result['evidence_summary']['tools_requested'] == 2
    assert result['evidence_summary']['tools_run'] == 2
    assert result['evidence_summary']['repo_size_bytes'] == 17
    assert parent['finding_count'] == 4 and parent['evidence_summary']['tools_run'] == 1


@pytest.mark.parametrize('parent_status,child_status', [('running', 'complete'), ('complete', 'running'),
    ('queued', 'queued'), ('failed', 'running'), ('unavailable', 'running')])
def test_either_active_execution_keeps_composite_running(parent_status, child_status):
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population(parent_status, child_status)
    result = compose_cpp_scan(parent, child, job)
    assert result['status'] == 'running'
    assert result['ordinary_scan_status'] == parent_status
    assert result['cpp_worker_status'] == child_status


@pytest.mark.parametrize('field', ['customer_id', 'project_id', 'run_id', 'repository', 'snapshot_id',
    'snapshot_commit_sha', 'scan_id', 'worker_job_id', 'parent_scan_id', 'provider_access_mode', 'provider_credential_used'])
def test_child_identity_substitution_is_rejected_before_join(field):
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population(); child[field] = 'foreign'
    with pytest.raises(JobConflict, match='cpp_child'):
        compose_cpp_scan(parent, child, job)


@pytest.mark.parametrize('field', ['release_revision', 'contract_sha256'])
def test_parent_identity_freezes_contract_and_release(field):
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population()
    parent['cpp_worker_child']['identity'][field] = 'f' * len(job['identity'][field])
    with pytest.raises(JobConflict, match='cpp_child'):
        compose_cpp_scan(parent, child, job)


@pytest.mark.parametrize('state', ['failed', 'cancelled', 'blocked'])
def test_terminal_child_failure_retains_ordinary_evidence_without_cpp_success(state):
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population(child_status=state)
    result = compose_cpp_scan(parent, child, job)
    assert result['scanner_results'][0] == parent['scanner_results'][0]
    assert result['tools_run'] == ['bandit']
    missing = result['scanner_results'][1]
    assert missing['verified_complete'] is False and missing['findings'] == []
    assert 'cppcheck' in result['failed_tools'] and result['status'] == 'complete'
    assert result['finding_summary']['raw_total'] == 0


def test_cpp_success_does_not_erase_ordinary_execution_limit():
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population(parent_status='unavailable')
    parent['execution_limit'] = {'reason': 'repository_size_limit_exceeded', 'scanner_execution_permitted': False}
    result = compose_cpp_scan(parent, child, job)
    assert result['execution_limit'] == parent['execution_limit'] and result['status'] == 'unavailable'
    assert result['scanner_results'][0] == parent['scanner_results'][0]


def test_closed_parent_never_revives_on_late_child_completion():
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population(parent_status='cancelled')
    assert compose_cpp_scan(parent, child, job)['status'] == 'cancelled'


@pytest.mark.parametrize('change', ['no_receipt', 'unfinished_job', 'wrong_revision', 'unverified_checkout'])
def test_inconsistent_child_completion_cannot_be_promoted(change):
    from nico.assessment_cpp_integration import compose_cpp_scan
    parent, child, job = population()
    if change == 'no_receipt': child['scanner_results'] = []
    elif change == 'unfinished_job': job['status'] = 'queued'
    elif change == 'wrong_revision': child['actual_commit_sha'] = 'f' * 40
    else: child['snapshot_match'] = False
    with pytest.raises(JobConflict, match='completion_unverified'):
        compose_cpp_scan(parent, child, job)


def test_late_ordinary_write_cannot_replace_durable_operator_close(monkeypatch):
    from nico import assessment_cpp_integration as integration, snapshot_scanner_worker as worker
    from nico.storage import MemoryAdapter
    parent, _, _ = population(parent_status='queued', child_status='queued')
    store = MemoryAdapter()
    store.put('scanner_runs', parent['scan_id'], parent)
    monkeypatch.setattr(worker, 'STORE', store)
    monkeypatch.setitem(worker.base.SCAN_JOBS, parent['scan_id'], deepcopy(parent))
    def publish(value, _adapter):
        current = store.get('scanner_runs', value['scan_id'])
        if current['status'] not in {'queued', 'running'}:
            return False
        store.put('scanner_runs', value['scan_id'], value)
        return True
    monkeypatch.setattr(integration, 'publish_cpp_parent', publish, raising=False)
    def close_during_checkout(*_args):
        current = store.get('scanner_runs', parent['scan_id'])
        current.update(status='cancelled', recovery={'state': 'closed_by_operator'})
        store.put('scanner_runs', parent['scan_id'], current)
        return None, '', ['Synthetic cancellation during checkout; no repository executed.']
    monkeypatch.setattr(worker, 'clone_repository_at_snapshot', close_during_checkout)
    worker._run_snapshot_scan(parent['scan_id'], {'repository': parent['repository'],
        'snapshot_commit_sha': parent['snapshot_commit_sha'], 'tools': ['bandit']})
    current = store.get('scanner_runs', parent['scan_id'])
    assert current['status'] == 'cancelled'
    assert current['recovery']['state'] == 'closed_by_operator'


def test_resumed_parent_preserves_anonymous_acquisition_mode():
    from nico.snapshot_scanner_resilience_patch import _snapshot_resume_payload
    parent, _, _ = population(parent_status='recovery_required', child_status='running')
    payload = _snapshot_resume_payload(parent)
    assert payload['provider_access_mode'] == 'anonymous_public'
    assert payload['provider_credential_used'] is False
