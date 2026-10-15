"""Owned authenticated transcripts and real immutable SQLite artifact persistence."""
import copy
import gzip
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from test_nico_ci_typescript_consumer import api, retained, project, setup_capture, NOW, SPEC, bomb
from test_nico_ci_typescript_github import failed_check, replace_archive
from test_nico_ci_typescript_evidence import revise
from nico import nico_ci_typescript_consumer_v1 as consumer
from nico import scanner_evidence_pipeline_v1 as pipeline
from nico import scanner_raw_artifact_storage_v1 as storage
from nico import comprehensive_scanner_inventory_v1 as inventory
from nico import complete_assessment_gate_v1 as gate
from nico import v2_snapshot_scanner_authority as snapshot
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from nico.worker_execution import WorkerWorkspace

BASIS = 'authenticated_retained_typescript_ci'
SHA = 'b' * 40


@pytest.fixture
def display_value(request):
    return getattr(request, 'param', None)


@pytest.fixture
def persisted_case(api, retained, monkeypatch, tmp_path, outcome, display_value):
    if outcome != 'clean':
        def change(record, native):
            for value in (record, native):
                value.update(clean=False, diagnostics=[{'code':2322, 'category':'Error', 'message':'owned error'}], diagnostics_text='owned error')
                if display_value is not None:
                    value['diagnostics'][0]['message'] = display_value
                    value['diagnostics_text'] = display_value
                    value['effective_configuration']['paths'] = {'fixture': [display_value]}
                    value['configuration_limitations']['fixture_description'] = display_value
            record['raw_exit_code'] = 1
            if outcome == 'incomplete':
                record.update(status='incomplete', capture_complete=False, capture_truncated=True, reason='capture_incomplete')
                native.clear()
        archive, _ = revise(retained, change)
        failed_check(api)
        api = replace_archive(api, archive)
    client, _ = setup_capture(api, monkeypatch)
    imported, archive = consumer.collect(client, SHA, 300, now=NOW)
    monkeypatch.setattr(consumer, '_capture_bounded', lambda *a: (imported, archive))
    monkeypatch.setattr(pipeline, '_git_text', lambda *a: SHA)
    monkeypatch.setattr(snapshot, '_commit_sha', lambda *a: SHA)
    monkeypatch.setattr(snapshot, '_target_repository', lambda *a: 'BoneManTGRM/NICO')
    raw_root = tmp_path / 'raw'
    monkeypatch.setattr(snapshot, 'DEFAULT_RAW_ROOT', raw_root)
    monkeypatch.setattr(inventory, 'DEFAULT_RAW_ROOT', raw_root)
    workspace = WorkerWorkspace(tmp_path / 'worker')
    workspace.repo_dir.mkdir(parents=True)
    monkeypatch.setattr(pipeline, '_owned_nico_ci', lambda *a: True)
    monkeypatch.setattr(pipeline, 'node_inapplicability_result', lambda *a: None)
    monkeypatch.setattr(pipeline, 'verify_source_checkout', lambda payload, *a: payload)
    payload = snapshot.canonical_snapshot_tool_runner(SPEC, workspace, runner=bomb)
    binding = dict(run_id='comprun_owned_status', scan_id='scan_owned_status', customer_id='owned_customer',
                   project_id='owned_project', repository='BoneManTGRM/NICO', commit_sha=SHA, scanner_name='typescript')
    database = tmp_path / 'artifacts.sqlite3'
    def reopen():
        return storage.ScannerArtifactStore(lambda: sqlite3.connect(database), dialect='sqlite')
    store = reopen()
    store.ensure_schema()
    monkeypatch.setattr(storage, '_default_store', reopen)
    record = storage.persist_scanner_result(payload, binding=binding, raw_root=raw_root)
    read = storage.read_scanner_artifact(record, binding=binding, raw_root=raw_root)
    assert read.metadata['availability'] == 'verified'
    assert read.compressed == (raw_root / payload['raw_artifact']['storage_key']).read_bytes()
    case = SimpleNamespace(record=record, binding=binding, raw=read.raw, raw_root=raw_root, store=reopen())
    # Other tools are explicit positive controls, as in the original persistence
    # test. Only their raw-reader result is stubbed; TypeScript uses real storage.
    original_raw = inventory._raw_metadata
    monkeypatch.setattr(inventory, '_raw_metadata', lambda row, **kw: original_raw(row, **kw)
        if row.get('scanner_name') == 'typescript' else {'availability':'verified', 'sha256':'a'*64})
    return case


def evaluate(case, monkeypatch):
    binding = case.binding
    identity = {k:v for k,v in binding.items() if k not in {'scan_id', 'scanner_name'}}
    controls = [{**binding, 'scanner_name':name, 'tool':name, 'status':'completed',
                 'verified_complete':True, 'execution_observed_for_this_report':True,
                 'output_capture_complete':True, 'output_truncated':False, 'timed_out':False,
                 'source_checkout_verified':True, 'applicable':True, 'returncode_valid':True,
                 'raw_artifact_retention_complete':True, 'raw_artifact_sha256':'a'*64}
                for name in gate.REQUIRED_TOOLS if name != 'typescript']
    scan = {**binding, 'snapshot_commit_sha':SHA, 'actual_commit_sha':SHA, 'snapshot_match':True,
            'tools_requested':list(gate.REQUIRED_TOOLS), 'scanner_results':controls+[case.record]}
    monkeypatch.setattr(inventory, 'get_scan', lambda _: scan)
    records = compact_scanner_records(scan, commit_sha=SHA)
    canonical = {'identity':identity, 'scanner_execution_records':records}
    status = {**identity, 'revision':1, 'terminal':True,
              'scanner_execution_summary':{'completed_tools':list(gate.REQUIRED_TOOLS),
                  'applicable_tools':list(gate.REQUIRED_TOOLS), 'not_applicable_tools':[]},
              'scanner_evidence_binding':{'identity':identity, 'revision':1,
                  'stage_results':{'dependency_security_static_analysis':{'scan_id':binding['scan_id']}},
                  'scanner_artifact_sha256s':{r['tool']:r['raw_artifact_sha256'] for r in records}}}
    return canonical, inventory.verify_status_scanner_evidence(status)


def replace_projection(case, mutate):
    body = json.loads(case.raw)
    mutate(body)
    raw = json.dumps(body).encode()
    compressed = gzip.compress(raw, mtime=0)
    # New immutable synthetic row, never overwrite existing artifact bytes.
    case.binding = {**case.binding, 'scan_id':case.binding['scan_id']+'_negative'}
    case.record.update(case.binding)
    digest = hashlib.sha256(raw).hexdigest()
    artifact_id = case.store.put(case.binding, compressed, digest)
    case.record['raw_artifact'].update(artifact_id=artifact_id, sha256=digest,
        gzip_sha256=hashlib.sha256(compressed).hexdigest(), retained_bytes=len(raw), gzip_bytes=len(compressed))
    case.record['raw_artifact_sha256'] = digest


@pytest.mark.parametrize('outcome', ['clean', 'errors'])
def test_authenticated_retained_ci_gets_ordinary_coverage_not_native_execution(persisted_case, monkeypatch, outcome):
    case = persisted_case
    before = copy.deepcopy(case.record)
    canonical, status = evaluate(case, monkeypatch)
    row = next(r for r in status['scanner_evidence_verification']['scanner_records'] if r['scanner_name']=='typescript')
    assert row['raw_artifact']['availability'] == 'verified'
    assert row['coverage_basis'] == BASIS
    assert row['execution_observed'] is False
    assert case.record['execution_observed_for_this_report'] is False and case.record['current_run'] is False
    assert status['scanner_evidence_verification']['failures'] == []
    assert status['scanner_execution_summary']['completed_count'] == 9
    assert status['scanner_execution_summary']['retained_ci_tools'] == ['typescript']
    assert case.record == before
    record = next(r for r in canonical['scanner_execution_records'] if r['tool']=='typescript')
    assert record['finding_count'] == (0 if outcome=='clean' else 1)
    if outcome == 'errors':
        assert case.record['findings'][0]['message'] == 'owned error'
        assert record['status'] == 'completed_with_findings'
    with pytest.raises(gate.ScannerEvidenceBlocked) as caught:
        gate.require_retained_assessment(canonical, status, expected_commit=SHA, expected_run=case.binding['run_id'])
    assert 'typescript:native_execution_incomplete' in caught.value.evidence['failures']


@pytest.mark.parametrize('outcome,damage', [('incomplete', None)] + [('clean', x) for x in (
    'wrong_source', 'wrong_binding', 'raw_digest', 'missing_provenance', 'caller_flags',
    'ci_identity', 'ci_digest', 'missing_import', 'wrong_workflow', 'diagnostics', 'native_conflict',
    'missing_bytes',
)])
def test_unproven_retained_ci_never_gains_coverage(persisted_case, monkeypatch, outcome, damage):
    case = persisted_case
    if damage == 'wrong_source': case.record['ci_source_sha'] = 'c'*40
    elif damage == 'wrong_binding': case.record['customer_id'] = 'other'
    elif damage == 'raw_digest': case.record['raw_artifact']['sha256'] = 'c'*64
    elif damage == 'missing_provenance': case.record.pop('ci_run_attempt')
    elif damage == 'missing_bytes':
        # Remove only the disposable fixture row. A surviving local capture or
        # caller-supplied coverage label cannot replace the durable bytes.
        case.record['coverage_basis'] = BASIS
        with case.store.connect() as connection:
            connection.execute('DELETE FROM scanner_raw_artifacts WHERE artifact_id=?',
                               (case.record['raw_artifact']['artifact_id'],))
            connection.commit()
    elif damage == 'caller_flags':
        case.record.update(coverage_basis=BASIS, metadata_authenticated=True)
        replace_projection(case, lambda body: body.pop('authenticated_import'))
    elif damage == 'ci_identity': case.record['ci_run_id'] = '999999'
    elif damage == 'ci_digest': case.record['ci_artifact_digest'] = 'sha256:'+'c'*64
    elif damage == 'missing_import': replace_projection(case, lambda body: body['authenticated_import'].pop('metadata_authenticated'))
    elif damage == 'wrong_workflow': replace_projection(case, lambda body: body['members']['typescript.json'].update(workflow_ref='other'))
    elif damage == 'diagnostics': replace_projection(case, lambda body: body['authenticated_import'].update(clean=False))
    elif damage == 'native_conflict': replace_projection(case, lambda body: body['members']['typescript.log'].update(diagnostics=[] if outcome=='errors' else [{'code':1,'category':'Error','message':'changed'}]))
    _, status = evaluate(case, monkeypatch)
    assert 'typescript' not in status['scanner_evidence_verification']['verified_tools']
    assert 'typescript' in status['scanner_execution_summary']['incomplete_tools']
    row = next(r for r in status['scanner_evidence_verification']['scanner_records'] if r['scanner_name']=='typescript')
    assert row.get('coverage_basis') != BASIS
    assert row['execution_observed'] is False


@pytest.mark.parametrize('outcome', ['errors'])
def test_retained_error_cannot_be_erased_from_worker_findings(persisted_case, monkeypatch):
    persisted_case.record.update(findings=[], findings_count=0, finding_count=0)
    _, status = evaluate(persisted_case, monkeypatch)
    assert 'typescript' not in status['scanner_evidence_verification']['verified_tools']


@pytest.mark.parametrize('outcome', ['clean'])
def test_unsupported_scanner_cannot_reuse_retained_ci_basis(persisted_case):
    from nico.retained_typescript_status_v1 import verified_retained_typescript
    case = persisted_case
    binding = {**case.binding, 'scanner_name':'eslint'}
    compressed = gzip.compress(case.raw, mtime=0)
    record = copy.deepcopy(case.record)
    record.update(binding)
    record['raw_artifact'].update(artifact_id=case.store.put(binding, compressed, hashlib.sha256(case.raw).hexdigest()),
                                 gzip_sha256=hashlib.sha256(compressed).hexdigest(), gzip_bytes=len(compressed))
    read = storage.read_scanner_artifact(record, binding=binding, raw_root=case.raw_root)
    assert read.metadata['availability'] == 'verified'
    assert verified_retained_typescript(record, binding, read) is False


@pytest.mark.parametrize('outcome', ['clean'])
def test_changed_durable_bytes_fail_closed(persisted_case, monkeypatch):
    case = persisted_case
    # Damage only this disposable SQLite fixture; immutable production APIs are
    # not bypassed by the implementation. Reader must detect byte corruption.
    with case.store.connect() as connection:
        connection.execute('UPDATE scanner_raw_artifacts SET gzip_blob=? WHERE artifact_id=?',
                           (b'changed', case.record['raw_artifact']['artifact_id']))
        connection.commit()
    _, status = evaluate(case, monkeypatch)
    row = next(r for r in status['scanner_evidence_verification']['scanner_records'] if r['scanner_name']=='typescript')
    assert row['raw_artifact']['availability'] == 'compressed_checksum_mismatch'
    assert row.get('coverage_basis') != BASIS
    assert 'typescript' not in status['scanner_evidence_verification']['verified_tools']


@pytest.mark.parametrize('outcome', ['errors'])
@pytest.mark.parametrize('display_value', ['owned\x00message', 'owned\ud800message'], indirect=True,
                         ids=['nul', 'lone-surrogate'])
def test_display_escaping_preserves_retained_coverage(persisted_case, monkeypatch, display_value):
    case = persisted_case
    before = copy.deepcopy(case.record)
    original = json.loads(case.raw)['authenticated_import']
    expected = storage._jsonb_display_text({'value': display_value})['value']
    assert original['diagnostics'][0]['message'] == display_value
    assert case.record['diagnostics'][0]['message'] == expected != display_value
    assert case.record['findings'][0]['message'] == expected
    assert case.record['effective_configuration']['paths']['fixture'] == [expected]
    assert case.record['configuration_limitations']['fixture_description'] == expected
    canonical, status = evaluate(case, monkeypatch)
    assert 'typescript' in status['scanner_evidence_verification']['verified_tools']
    assert status['scanner_execution_summary']['retained_ci_tools'] == ['typescript']
    assert case.record == before
    assert case.record['execution_observed_for_this_report'] is False
    assert case.record['current_run'] is False
    read = storage.read_scanner_artifact(case.record, binding=case.binding, raw_root=case.raw_root)
    assert read.raw == case.raw
    assert read.metadata['sha256'] == before['raw_artifact_sha256']
    with pytest.raises(gate.ScannerEvidenceBlocked) as caught:
        gate.require_retained_assessment(canonical, status, expected_commit=SHA, expected_run=case.binding['run_id'])
    assert 'typescript:native_execution_incomplete' in caught.value.evidence['failures']


@pytest.mark.parametrize('outcome', ['errors'])
@pytest.mark.parametrize('display_value', ['owned\x00message', 'owned\ud800message'], indirect=True,
                         ids=['nul', 'lone-surrogate'])
@pytest.mark.parametrize('damage', ['diagnostic', 'finding', 'configuration', 'raw_native'])
def test_display_escaping_does_not_accept_changed_evidence(persisted_case, monkeypatch, damage):
    case = persisted_case
    if damage == 'diagnostic':
        case.record['diagnostics'][0]['message'] += 'changed'
    elif damage == 'finding':
        case.record['findings'][0]['message'] += 'changed'
    elif damage == 'configuration':
        case.record['effective_configuration']['paths']['fixture'].append('changed')
    else:
        # Escaped display text and the original codepoint must not compare equal
        # between raw import/native evidence, even if their display forms match.
        def change(body):
            for member in ('typescript.json', 'typescript.log'):
                diagnostic = body['members'][member]['diagnostics'][0]
                diagnostic['message'] = case.record['diagnostics'][0]['message']
        replace_projection(case, change)
    _, status = evaluate(case, monkeypatch)
    assert 'typescript' not in status['scanner_evidence_verification']['verified_tools']
