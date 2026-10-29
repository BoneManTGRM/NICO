from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from nico import candidate_workspace_capture_v1 as capture
from nico.candidate_investigation_pipeline_v1 import investigate_register, display_investigation
from tests.test_candidate_investigation_pipeline_v1 import SCOPE
from tests.test_candidate_source_observations_v1 import row


def memory(files):
    blobs = {}
    entries = {}
    for path, data in files.items():
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data, usedforsecurity=False).hexdigest()
        blobs[oid] = data
        entries[path] = (oid, len(data))
    reads = []
    def read(oid, size, deadline):
        reads.append(oid)
        return blobs[oid]
    return lambda deadline, paths: entries, read, reads


def test_selection_is_deterministic_unique_and_preserves_all_candidates():
    rows = [row(candidate_id='other', source_path='a.py', rule_id='B999'),
            row(candidate_id='first', source_path='./z.py'), row(candidate_id='duplicate', source_path='z.py')]
    inventory, read, reads = memory({'a.py': b'assert x\n', 'z.py': b'assert y\n'})
    before = deepcopy(rows)
    result = capture.capture_candidates(rows, SCOPE, inventory, read)
    assert list(result['observations']) == ['z.py', 'a.py']
    assert len(reads) == 2
    reverse = capture.capture_candidates(list(reversed(rows)), SCOPE, inventory, read)
    assert result['observations'] == reverse['observations']
    packets = investigate_register({'findings': rows}, result, SCOPE)
    assert packets['candidate_count'] == 3
    assert packets['bounded_rule_analysis_completed'] == 2
    assert rows == before


@pytest.mark.parametrize('path', ['../outside.py', '/tmp/outside.py', 'a/../../x.py', 'a\\x.py', '.git/x.py', 'a\x00.py', 'https://x.py', 'file.js'])
def test_unsafe_or_unsupported_paths_never_request_source(path):
    inventory, read, reads = memory({'safe.py': b'assert x\n'})
    result = capture.capture_candidates([row(source_path=path)], SCOPE, inventory, read)
    assert result['observations'] == {} and reads == []


@pytest.mark.parametrize('field,value', [('exact_commit_sha','f'*40), ('source_commit_sha','f'*40), ('source_repository','other/repo')])
def test_foreign_candidate_identity_cannot_select_source(field, value):
    inventory, read, reads = memory({'example.py': b'assert x\n'})
    result = capture.capture_candidates([row(**{field:value})], SCOPE, inventory, read)
    assert not result['observations'] and not reads


def test_missing_and_capped_inventory_are_explicit(monkeypatch):
    monkeypatch.setattr(capture, 'CANDIDATE_LIMIT', 2)
    inventory, read, reads = memory({})
    rows = [row(candidate_id=str(i), source_path=f'{i}.py') for i in range(3)]
    result = capture.capture_candidates(rows, SCOPE, inventory, read)
    assert result['candidate_record_count'] == 3
    assert result['candidate_records_considered'] == 2
    assert result['candidate_inventory_complete'] is False
    assert result['unavailable_reasons'] == {'candidate_inventory_limit': 1, 'source_missing_or_unsupported': 2}
    assert investigate_register({'findings': rows}, result, SCOPE)['candidate_count'] == 3


def test_input_bytes_charged_once_even_for_bad_hash(monkeypatch):
    monkeypatch.setattr(capture, 'INPUT_LIMIT', 10)
    inventory, read, reads = memory({'a.py': b'assert x\n', 'b.py': b'assert y\n'})
    result = capture.capture_candidates([row(source_path='a.py'), row(source_path='b.py')], SCOPE, inventory, lambda *args: b'bad')
    assert result['source_bytes_read'] == 9
    assert result['unavailable_reasons']['source_analysis_failed'] == 1
    assert result['unavailable_reasons']['source_size_budget'] == 1


def test_multibyte_observation_is_limited_by_encoded_bytes(monkeypatch):
    monkeypatch.setattr(capture, 'OUTPUT_LIMIT', 40000)
    monkeypatch.setattr(capture, 'observe_python_source', lambda *a, **k: {'status':'parsed', 'value':'漢'*3000})
    inventory, read, reads = memory({'example.py': b'assert x\n'})
    result = capture.capture_candidates([row()], SCOPE, inventory, read)
    assert not result['observations']
    assert result['unavailable_reasons']['observation_size_budget'] == 1
    assert len(capture.encoded(result)) <= 40000


def test_shared_deadline_includes_selection_and_discards_overrun(monkeypatch):
    now = [0.0]
    inventory, read, reads = memory({'example.py': b'assert x\n'})
    def slow_inventory(deadline, paths):
        assert deadline == 5
        now[0] = 5
        return inventory(deadline, paths)
    result = capture.capture_candidates([row()], SCOPE, slow_inventory, read, started=0, clock=lambda: now[0])
    assert not reads and result['deadline_exhausted']
    assert result['unavailable_reasons']['source_time_budget'] == 1
    now[0] = 0
    real = capture.observe_python_source
    def slow_parse(*args, **kwargs):
        observed = real(*args, **kwargs)
        now[0] = 5.1
        return observed
    monkeypatch.setattr(capture, 'observe_python_source', slow_parse)
    result = capture.capture_candidates([row()], SCOPE, inventory, read, clock=lambda: now[0])
    assert not result['observations'] and result['deadline_exhausted']


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()
    git('init', '-q')
    (repo / 'example.py').write_text('assert permitted\n')
    (repo / 'linked.py').symlink_to('/etc/passwd')
    git('add', '.')
    git('-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'synthetic fixture')
    return repo, git('rev-parse', 'HEAD')


def scan_results():
    return [{'tool':'bandit', 'category':'static', 'status':'completed', 'findings':[
        {'filename':'./example.py', 'line_number':1, 'test_id':'B101', 'issue_text':'assert observation'},
        {'filename':'linked.py', 'line_number':1, 'test_id':'B101', 'issue_text':'link observation'}]}]


def test_workspace_uses_verified_git_blobs_not_mutated_checkout_or_symlinks(repository):
    repo, sha = repository
    (repo / 'example.py').write_text('raise RuntimeError("must not execute")\n')
    scope = {**SCOPE, 'commit_sha':sha, 'snapshot_commit_sha':sha}
    result = capture.capture_workspace(repo, scope, sha, scan_results(), env=os.environ.copy())
    assert set(result['observations']) == {'example.py'}
    assert result['unavailable_reasons']['source_missing_or_unsupported'] == 1
    reg = {'findings':[row(exact_commit_sha=sha)]}
    packet = investigate_register(reg, result, scope)
    assert packet['bounded_rule_analysis_completed'] == 1
    assert display_investigation({**reg, 'candidate_investigation':packet}, scope)['completed_count'] == 1
    bad = capture.capture_workspace(repo, scope, 'f'*40, scan_results(), env=os.environ.copy())
    assert not bad['observations']


def test_real_worker_captures_once_before_cleanup_despite_partial_failure(repository, monkeypatch):
    from nico import snapshot_scanner_worker as worker
    from nico import scanner_raw_artifact_storage_v1 as storage
    repo, sha = repository
    saved, roots, captures = [], [], []
    def clone(repository, revision, root, env):
        target = root / 'repo'
        subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(repo), str(target)], check=True)
        roots.append(root)
        return target, sha, []
    monkeypatch.setattr(worker, 'clone_repository_at_snapshot', clone)
    monkeypatch.setattr(worker, '_persist_snapshot_scan', lambda record: saved.append(deepcopy(record)) or True)
    specs = [SimpleNamespace(name='bandit',category='static',scans_git_history=False),
             SimpleNamespace(name='eslint',category='static',scans_git_history=False)]
    monkeypatch.setattr(worker, '_requested_specs', lambda payload: specs)
    monkeypatch.setattr(worker, '_requested_tool_names', lambda payload: ['bandit','eslint'])
    def scan(spec, workspace):
        if spec.name == 'eslint':
            raise ValueError('synthetic scanner failure')
        return scan_results()[0]
    monkeypatch.setattr(worker.tool_runners, 'run_scanner_tool', scan)
    monkeypatch.setattr(storage, 'persist_scanner_result', lambda result, **kwargs: result)
    monkeypatch.setattr(worker.STORE, 'audit', lambda *args, **kwargs: None)
    original = capture.capture_workspace
    def observed(*args, **kwargs):
        assert Path(args[0]).exists()
        captures.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(capture, 'capture_workspace', observed)
    payload = {**SCOPE, 'commit_sha':sha, 'snapshot_commit_sha':sha}
    job = {'scan_id':'synthetic-capture'}
    worker._run_snapshot_scan(job['scan_id'], payload, execution_record=job)
    completed = saved[-1]
    assert completed['candidate_source_capture_attempted'] is True
    assert set(completed['candidate_source_observations']['observations']) == {'example.py'}
    assert completed['failed_tools'] == ['eslint']
    assert all(not root.exists() for root in roots)
    worker._run_snapshot_scan(job['scan_id'], payload, execution_record=completed)
    assert len(captures) == 1
    assert saved[-1]['candidate_source_observations'] == completed['candidate_source_observations']
    assert all(not root.exists() for root in roots)


def test_reserved_interrupted_capture_does_not_run_again(repository, monkeypatch):
    # This is the persisted state after a crash between reservation and capture.
    from nico import snapshot_scanner_worker as worker
    repo, sha = repository
    saved = []
    monkeypatch.setattr(worker, 'clone_repository_at_snapshot', lambda *a: (repo, sha, []))
    monkeypatch.setattr(worker, '_persist_snapshot_scan', lambda record: saved.append(deepcopy(record)) or True)
    monkeypatch.setattr(worker, '_requested_specs', lambda p: [])
    monkeypatch.setattr(worker, '_requested_tool_names', lambda p: [])
    monkeypatch.setattr(worker.STORE, 'audit', lambda *a, **k: None)
    monkeypatch.setattr(capture, 'capture_workspace', lambda *a, **k: pytest.fail('duplicate budget'))
    worker._run_snapshot_scan('synthetic', {**SCOPE, 'snapshot_commit_sha':sha},
        execution_record={'candidate_source_capture_attempted':True})
    assert 'candidate_source_observations' not in saved[-1]


def test_scoring_handoff_preserves_capture_for_finalization_and_diagnostics(monkeypatch):
    from nico import comprehensive_native_providers as legacy, comprehensive_native_providers_v5 as v5
    from tests.test_comprehensive_native_providers_v2 import _context, _repo, _scan
    from nico.comprehensive_run_service import _prior_stage_results_for_stage
    from nico.candidate_capture_diagnostics import capture_diagnostics
    context, repo, scan = _context(), _repo(), _scan()
    inventory, read, _ = memory({'example.py': b'assert x\n'})
    source = capture.capture_candidates([row(exact_commit_sha=context['commit_sha'])], context, inventory, read)
    scan.update(candidate_source_capture_attempted=True, candidate_source_observations=source)
    monkeypatch.setattr(legacy, '_repo', lambda _: repo)
    monkeypatch.setattr(legacy, '_scan', lambda _: scan)
    monkeypatch.setattr(legacy, '_complexity', lambda _: {})
    result = v5.canonical_scoring_provider(context)
    assert result['candidate_source_observations'] == source
    stages = {'evidence_reconciliation_and_scoring': result}
    final_context = _prior_stage_results_for_stage('final_comprehensive_report_generation', stages, list(stages))
    assert final_context['evidence_reconciliation_and_scoring']['candidate_source_observations'] == source
    diagnostic = capture_diagnostics({'identity':context, 'stage_results': stages})
    assert diagnostic['capture_present'] and diagnostic['scope_match'] and diagnostic['observation_count'] == 1
    # A reserved/failed new capture cannot resurrect an old repository capture.
    repo['candidate_source_observations'] = source
    del scan['candidate_source_observations']
    failed = v5.canonical_scoring_provider(context)
    assert failed['candidate_source_observations'] is None
    assert failed['assessment']['canonical_scanner_finding_register']['candidate_investigation']['bounded_rule_analysis_completed'] == 0


def _installed_new_channel(repo_path, sha, language):
    from nico.api import final_report_worker_bootstrap
    from tests.test_roadmap_pdf_detail_completeness import _five_gap_package
    from nico.candidate_investigation_finalization_v1 import final_investigation_scope
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from nico.comprehensive_review_work_v2 import review_work_projection
    from nico.comprehensive_native_providers_v5 import build_canonical_scanner_finding_register
    from tests import test_v2_premium_report_renderer as base_fixture
    from unittest.mock import patch
    original_fixture = base_fixture._package
    def bound_fixture(locale):
        value = original_fixture(locale)
        value['json']['identity']['commit_sha'] = sha
        return value
    with patch.object(base_fixture, '_package', bound_fixture):
        package = _five_gap_package(language)
    identity = package['json']['identity']
    source = capture.capture_workspace(repo_path, {**identity, 'snapshot_commit_sha':sha}, sha, scan_results(), env=os.environ.copy())
    register = build_canonical_scanner_finding_register({'scanner_results':scan_results()}, sha)
    register['review_workload_clusters'] = [{'cluster_id':'synthetic', 'candidate_ids':[r['candidate_id'] for r in register['findings']]}]
    register['candidate_investigation'] = investigate_register(register, source, identity)
    package['json']['assessment']['canonical_scanner_finding_register'] = deepcopy(register)
    context = {**identity, 'prior_stage_results':{'evidence_reconciliation_and_scoring':{
        'candidate_source_observations': source, 'assessment':{'canonical_scanner_finding_register':register}}}}
    before = deepcopy(context)
    with final_investigation_scope(context):
        result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    retained = result['json']['assessment']['canonical_scanner_finding_register']
    assert retained['candidate_investigation'] == register['candidate_investigation']
    assert retained['final_candidate_investigation']['source_capture']['candidate_inventory_complete'] is True
    record = {'identity':identity, 'stage_results':{'final_comprehensive_report_generation':{'report_package':result}}}
    ui = review_work_projection(record)['review_assistance']['source_investigation']
    assert ui['available'] and ui['completed_count'] == 1 and ui['candidate_count'] == 2
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
    assert context == before


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_installed_workspace_to_final_artifacts_and_ui(repository, language, tmp_path):
    import sys
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    repo, sha = repository
    code = 'from tests.test_candidate_workspace_capture_v1 import _installed_new_channel; import sys; _installed_new_channel(*sys.argv[1:])'
    result = subprocess.run([sys.executable, '-c', code, str(repo), sha, language], cwd=root,
        env=owned_worker_environment(root, tmp_path, os.environ), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_metadata_is_charged_against_same_input_budget(monkeypatch):
    monkeypatch.setattr(capture, 'INPUT_LIMIT', 10)
    inventory, read, reads = memory({'example.py': b'assert x\n'})
    result = capture.capture_candidates([row()], SCOPE, lambda deadline, paths: (inventory(deadline, paths), 2), read)
    assert not reads and result['source_bytes_read'] == 0
    assert result['inventory_metadata_bytes'] == 2
    assert result['unavailable_reasons']['source_size_budget'] == 1


def test_malformed_oversized_scope_does_not_escape_output_bound():
    result = capture.capture_candidates([row()], {**SCOPE, 'repository':'x'*(capture.OUTPUT_LIMIT+1)},
        lambda *a: pytest.fail('must not read'), lambda *a: pytest.fail('must not read'))
    assert not result['observations']
    assert len(capture.encoded(result)) < capture.OUTPUT_LIMIT


def test_git_reads_disable_lazy_fetch_and_replacements(repository, monkeypatch):
    repo, sha = repository
    calls = []
    real = capture.subprocess.Popen
    def observed(args, **kwargs):
        calls.append(args)
        assert kwargs['env']['GIT_NO_LAZY_FETCH'] == '1'
        assert kwargs['env']['GIT_NO_REPLACE_OBJECTS'] == '1'
        assert kwargs['env']['GIT_LITERAL_PATHSPECS'] == '1'
        return real(args, **kwargs)
    monkeypatch.setattr(capture.subprocess, 'Popen', observed)
    result = capture.capture_workspace(repo, {**SCOPE, 'snapshot_commit_sha':sha}, sha, scan_results(), env=os.environ.copy())
    assert result['observations'] and all(args[0] == 'git' for args in calls)
    assert '--' in calls[0]
    assert result['total_input_bytes_charged'] <= capture.INPUT_LIMIT
    assert len(capture.encoded(result)) <= capture.OUTPUT_LIMIT
    assert result['retained_output_bytes'] == len(capture.encoded(result))
