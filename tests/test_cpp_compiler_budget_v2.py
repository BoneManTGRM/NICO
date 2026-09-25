"""Versioned compiler wall allocation cannot change populations or global limits."""
import base64
from copy import deepcopy
import inspect
import json
from pathlib import Path

import pytest
from nico import assessment_cpp_configuration_probe as probe
from nico import assessment_cpp_project_compiler as compiler
from nico import assessment_cpp_project_static as analysis
from nico import assessment_cpp_project_snapshot as snapshot
from tests.test_cpp_project_compiler import inputs, result_for, digest
from tests.test_cpp_baseline_execution import Native, source, contract
from tests.test_cpp_project_snapshot import _empty_native_snapshot


def versioned_request(tmp_path, version='v2'):
    raw, targets, captured, _ = inputs(tmp_path)
    assert 'extended_budget' in inspect.signature(compiler.project_compiler_request).parameters, (
        'missing explicitly versioned compiler allocation')
    request = compiler.project_compiler_request(raw, targets, captured, extended_budget=(version == 'v2'))
    return raw, targets, captured, request


def native_result(request, duration_ms=5):
    result = result_for(request)
    result['schema'] = request['schema'].replace('-request.', '-evidence.')
    result['duration_ms'] = duration_ms
    return result


def test_v2_allocates_600_seconds_without_changing_case_parallel_or_members(tmp_path):
    raw, targets, captured, request = versioned_request(tmp_path)
    legacy = compiler.project_compiler_request(raw, targets, captured)
    assert legacy['schema'] == 'nico.cpp-project-compiler-request.v1'
    assert legacy['limits'] == {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
    assert request['schema'] == 'nico.cpp-project-compiler-request.v2'
    assert request['limits'] == {'wall_seconds': 600, 'case_seconds': 90, 'parallel': 4}
    assert {k:v for k,v in request.items() if k not in {'schema','limits'}} == {
        k:v for k,v in legacy.items() if k not in {'schema','limits'}}
    assert len(request['contexts']) == 3
    assert request['contexts'][0]['context_id'] != request['contexts'][1]['context_id']


@pytest.mark.parametrize('version,limit', [('v1',543000),('v2',603000)])
def test_evidence_duration_bound_is_selected_by_exact_request_version(tmp_path, version, limit):
    _, _, _, request = versioned_request(tmp_path, version)
    result = native_result(request, limit)
    assert compiler.validate_project_compiler(compiler._canonical(result), request)['complete']
    result['duration_ms'] = limit + 1
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(result), request)


@pytest.mark.parametrize('change', ['version','wall','case','parallel','float','bool'])
def test_request_cannot_authorize_unbounded_or_mismatched_budget(tmp_path, change):
    _, _, _, request = versioned_request(tmp_path)
    if change == 'version': request['schema'] = 'nico.cpp-project-compiler-request.v99'
    if change == 'wall': request['limits']['wall_seconds'] = 601
    if change == 'case': request['limits']['case_seconds'] = 91
    if change == 'parallel': request['limits']['parallel'] = 5
    if change == 'float': request['limits']['wall_seconds'] = 600.0
    if change == 'bool': request['limits']['parallel'] = True
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(native_result(request)), request)


def test_old_and_new_evidence_cannot_be_relabelled_or_cross_bound(tmp_path):
    raw, targets, captured, modern = versioned_request(tmp_path)
    legacy = compiler.project_compiler_request(raw, targets, captured)
    for request, wrong in ((modern, legacy), (legacy, modern)):
        with pytest.raises(ValueError):
            compiler.validate_project_compiler(compiler._canonical(native_result(wrong)), request)
    result = native_result(modern)
    result['schema'] = 'nico.cpp-project-compiler-evidence.v1'
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(result), modern)


@pytest.mark.parametrize('version', ['v3', '', None, 2, 'v2'])
def test_unsupported_budget_rejected_before_plan_creation(tmp_path, version):
    raw, targets, captured, _ = versioned_request(tmp_path)
    with pytest.raises(ValueError):
        compiler.project_compiler_request(raw, targets, captured, extended_budget=version)


def test_static_consumer_binds_same_compiler_version_and_preserves_own_limit(tmp_path):
    raw, targets, captured, request = versioned_request(tmp_path)
    native = compiler._canonical(native_result(request, 550000))
    assert 'extended_compiler_budget' in inspect.signature(analysis.project_static_request).parameters
    static = analysis.project_static_request(raw, targets, captured, native, extended_compiler_budget=True)
    assert static['limits'] == {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
    assert static['compiler_evidence_sha256'] == digest(native)
    assert [r['context_id'] for r in static['contexts']] == [r['context_id'] for r in request['contexts']]
    with pytest.raises(ValueError):
        analysis.project_static_request(raw, targets, captured, native, extended_compiler_budget=False)


def test_embedded_collector_contains_same_budget_policy(tmp_path):
    _, _, _, request = versioned_request(tmp_path)
    namespace = {}
    exec(compiler.PROGRAM.rsplit('\nrun_project_compiler()\n', 1)[0], namespace)
    assert namespace['_compiler_limits'](request) == request['limits']
    request['limits']['wall_seconds'] = 10000
    with pytest.raises(ValueError):
        namespace['_compiler_limits'](request)


def probe_fixture(tmp_path, monkeypatch, *, version=None, failed=False, advance=1170,
                  late_boundary=None, elapsed=1799):
    root, targets = source(tmp_path)
    native = Native(targets)
    clock = [0.0]
    monkeypatch.setattr(probe.time, 'monotonic', lambda: clock[0])
    calls, saved, static_calls = [], [], []
    def command(argv, **options):
        calls.append((argv, options))
        if snapshot.PROJECT_SNAPSHOT_PROGRAM in argv:
            clock[0] = float(advance)
            raw = compiler._canonical(_empty_native_snapshot(json.loads(options['input_bytes'])))
        elif compiler.PROGRAM in argv:
            request = json.loads(options['input_bytes'])
            records = []
            for row in request['contexts']:
                dependencies = ('nico_unit: '+row['analysis_file']+'\n').encode()
                records.append({'context_id':row['context_id'],'invocation':row['invocation'],
                    'execution':{'exit_code':124 if failed else 0,'timed_out':failed,
                        'output_truncated':False,'duration_ms':1,'output':'','output_sha256':digest(b'')},
                    'dependency_bytes':base64.b64encode(dependencies).decode(),
                    'dependency_sha256':digest(dependencies),
                    'source_dependencies':{row['path']:targets[row['path']]},
                    'generated_dependencies':{},'toolchain_dependencies':[],'error':None})
            clock[0] += min(550.0, options['timeout'])
            raw = compiler._canonical({'schema':request['schema'].replace('-request.','-evidence.'),
                'request_sha256':digest(compiler._canonical(request)),'analyst_uid':1001,
                'records':records,'duration_ms':540000 if failed else 550000})
            if late_boundary == 'native-return':
                clock[0] = float(elapsed)
        else:
            return native(argv, **options)
        return {'exit_code':0,'timed_out':False,'output_truncated':False,'output':raw}
    def retain_artifact(key, raw):
        if key == 'project-compiler-evidence' and late_boundary == 'artifact-retention':
            clock[0] = float(elapsed)
        return {'path':'artifacts/'+key+'-'+digest(raw)+'.json','sha256':digest(raw),'bytes':len(raw)}
    def run_static(*args, **kwargs):
        assert any(argv[1:3] == ['rm','--force'] for argv, _ in calls)
        static_calls.append(kwargs)
        return {'complete':True, 'analysis':{'complete':True}}
    monkeypatch.setattr(analysis, 'run_project_static_stage', run_static)
    real_validate = compiler.validate_project_compiler
    def validate(raw, request):
        result = real_validate(raw, request)
        if late_boundary == 'validation':
            clock[0] = float(elapsed)
        return result
    monkeypatch.setattr(compiler, 'validate_project_compiler', validate)
    kwargs = {}
    if version is not None:
        assert 'extended_compiler_budget' in inspect.signature(probe.probe_project_configuration).parameters
        kwargs['extended_compiler_budget'] = (version == 'v2')
    result = probe.probe_project_configuration(root, targets, 'sha256:'+'a'*64,
        project_options={'BUILD_TESTS':'ON'}, baseline_execution=contract(),
        capture_generated_context=True, project_compiler_evidence=True, project_static_analysis=True,
        command=command, retain_artifact=retain_artifact,
        retain=lambda r:saved.append(deepcopy(r)), **kwargs)
    return result, calls, saved, static_calls


def test_probe_uses_v2_and_preserves_overall_deadline_before_separate_static_stage(tmp_path, monkeypatch):
    result, calls, saved, static_calls = probe_fixture(tmp_path, monkeypatch, version='v2')
    assert result['status'] == 'BASELINE_EXECUTED'
    assert result['compiled'] and result['tests_passed'] and result['project_compiler']['complete']
    assert result['execution_budget_seconds'] == 1800 and result['wall_budget_seconds'] == 1810
    assert result['aggregate_execution_budget_seconds'] == 2820
    invocation, options = next((a,k) for a,k in calls if compiler.PROGRAM in a)
    assert options['timeout'] == 610 and '--user=1001:1001' in invocation
    assert result['project_compiler_budget_version'] == 'v2'
    assert static_calls[0]['extended_compiler_budget'] is True
    assert saved[-1] == result


def test_v2_compiler_allocation_cannot_extend_parent_deadline(tmp_path, monkeypatch):
    result, calls, _, _ = probe_fixture(tmp_path, monkeypatch, version='v2', failed=True, advance=1760)
    _, options = next((a,k) for a,k in calls if compiler.PROGRAM in a)
    assert options['timeout'] == 40
    assert result['status'] == 'UNPROVEN' and not result['full_project_qualified']


def test_early_compiler_failure_retains_nonzero_aggregate_elapsed_time(tmp_path, monkeypatch):
    result, _, saved, static_calls = probe_fixture(tmp_path, monkeypatch, failed=True)
    assert result['compiled'] and result['tests_passed'] and result['cleanup_verified']
    assert result['status'] == 'UNPROVEN' and not static_calls
    assert result['duration_ms'] > 0
    assert result['aggregate_duration_ms'] == result['duration_ms'], 'failure loses aggregate execution time'
    assert saved[-1] == result


def test_both_owned_and_large_qualification_use_v2_without_global_budget_change():
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root/'.github/workflows/cpp-full-project-integration.yml').read_text())
    for name in ['owned-project-integration','project-baseline-qualification']:
        runs = '\n'.join(s.get('run','') for s in workflow['jobs'][name]['steps'])
        assert '--extended-compiler-budget' in runs
    assert workflow['jobs']['project-baseline-qualification']['timeout-minutes'] == 155
    assert workflow['permissions'] == {'contents':'read'}
    assert 'tests/test_cpp_compiler_budget_v2.py' in json.dumps(workflow['jobs']['contract-regressions'])


@pytest.mark.parametrize('boundary', ['native-return','artifact-retention','validation'])
@pytest.mark.parametrize('elapsed', [1799,1800,1801])
def test_compiler_cannot_promote_evidence_at_or_after_parent_deadline(tmp_path, monkeypatch, boundary, elapsed):
    result, _, saved, static_calls = probe_fixture(tmp_path, monkeypatch, version='v2',
        late_boundary=boundary, elapsed=elapsed)
    operation = next(op for op in result['operations'] if op['id'] == 'project-compiler-evidence')
    assert operation['output_artifact']['sha256'] == operation['output_sha256']
    assert result['compiled'] and result['tests_passed'] and result['cleanup_verified']
    assert result['aggregate_duration_ms'] == elapsed * 1000
    assert saved[-1] == result
    if elapsed < 1800:
        assert result['status'] == 'BASELINE_EXECUTED' and static_calls
    else:
        assert result['status'] == 'UNPROVEN' and not static_calls
        assert result['error'] == 'worker_configuration_probe_deadline'
