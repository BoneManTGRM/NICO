"""Budget v2 is opt-in; old native receipts retain their original 540s contract."""
import base64
from copy import deepcopy
import inspect

import pytest

from nico import assessment_cpp_project_compiler as compiler
from nico import assessment_cpp_project_static as static
from tests.test_cpp_project_compiler import inputs, result_for


def extended_request(tmp_path):
    database, targets, snapshot, _ = inputs(tmp_path)
    assert 'extended_budget' in inspect.signature(compiler.project_compiler_request).parameters, (
        'The measured full-population compiler replay needs a versioned 600-second budget')
    return compiler.project_compiler_request(database, targets, snapshot, extended_budget=True)


def evidence(request, *, duration_ms=10):
    value = result_for(request)
    value['schema'] = 'nico.cpp-project-compiler-evidence.v2'
    value['request_sha256'] = compiler._digest(compiler._canonical(request))
    value['duration_ms'] = duration_ms
    return value


def test_versioned_budget_preserves_population_commands_and_legacy_default(tmp_path):
    request = extended_request(tmp_path)
    legacy = deepcopy(request)
    legacy['schema'] = 'nico.cpp-project-compiler-request.v1'
    legacy['limits'] = {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
    database, targets, snapshot, _ = inputs(tmp_path / 'legacy')
    assert compiler.project_compiler_request(database, targets, snapshot) == legacy
    assert request['schema'] == 'nico.cpp-project-compiler-request.v2'
    assert request['limits'] == {'wall_seconds': 600, 'case_seconds': 90, 'parallel': 4}
    assert len(request['contexts']) == 3
    assert len({row['context_id'] for row in request['contexts']}) == 3
    assert request['targets'] == targets


def test_new_budget_accepts_completed_550_second_replay_without_relabeling_old_evidence(tmp_path):
    request = extended_request(tmp_path)
    result = evidence(request, duration_ms=550000)
    proof = compiler.validate_project_compiler(compiler._canonical(result), request)
    assert proof['complete'] is True
    assert proof['required_contexts'] == proof['checked_contexts']
    assert proof['static_analysis_executed'] is False
    result['schema'] = 'nico.cpp-project-compiler-evidence.v1'
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(result), request)


@pytest.mark.parametrize('field,value', [
    ('wall_seconds', 601), ('wall_seconds', True), ('case_seconds', 91),
    ('parallel', 5), ('parallel', 4.0)])
def test_no_unbounded_or_type_coerced_budget_is_accepted(tmp_path, field, value):
    request = extended_request(tmp_path)
    request['limits'][field] = value
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(evidence(request)), request)


def test_new_budget_still_rejects_total_case_and_aggregate_overruns(tmp_path):
    request = extended_request(tmp_path)
    result = evidence(request, duration_ms=603001)
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(result), request)
    result = evidence(request)
    result['records'][0]['execution']['duration_ms'] = 93001
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(result), request)
    result = evidence(request, duration_ms=10)
    result['records'][0]['execution']['duration_ms'] = 5000
    with pytest.raises(ValueError):
        compiler.validate_project_compiler(compiler._canonical(result), request)


def test_timed_out_last_context_remains_incomplete_under_new_budget(tmp_path):
    request = extended_request(tmp_path)
    result = evidence(request, duration_ms=600020)
    row = result['records'][-1]
    row['execution'].update(exit_code=124, timed_out=True, duration_ms=4600)
    proof = compiler.validate_project_compiler(compiler._canonical(result), request)
    assert proof['complete'] is False
    assert len(proof['required_contexts']) == len(proof['attempted_contexts']) == 3
    assert proof['checked_contexts'] == proof['required_contexts'][:-1]


def test_static_reconstruction_accepts_both_verified_compiler_budget_versions(tmp_path):
    request = extended_request(tmp_path)
    database, targets, snapshot, _ = inputs(tmp_path / 'static')
    value = evidence(request)
    plan = static.project_static_request(database, targets, snapshot, compiler._canonical(value))
    assert len(plan['contexts']) == 3
    assert plan['limits'] == {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}
    assert plan['compiler_evidence_sha256'] == compiler._digest(compiler._canonical(value))
    legacy = compiler.project_compiler_request(database, targets, snapshot)
    old_value = result_for(legacy)
    old_plan = static.project_static_request(database, targets, snapshot, compiler._canonical(old_value))
    assert plan['context_membership_sha256'] == old_plan['context_membership_sha256']
    assert [c['analyzer_invocation'] for c in plan['contexts']] == [c['analyzer_invocation'] for c in old_plan['contexts']]


def test_standalone_program_contains_enforced_budget_versions():
    namespace = {'__name__': 'embedded_budget_test'}
    exec(compiler.PROGRAM.rsplit('\nrun_project_compiler()', 1)[0], namespace)
    assert 'EXTENDED_LIMITS' in namespace, 'The isolated executor must receive the versioned budget'
    assert namespace['EXTENDED_LIMITS'] == {'wall_seconds': 600, 'case_seconds': 90, 'parallel': 4}
    assert namespace['LIMITS'] == {'wall_seconds': 540, 'case_seconds': 90, 'parallel': 4}


def test_probe_executes_versioned_budget_with_original_outer_envelope(tmp_path):
    from nico import assessment_cpp_configuration_probe as probe
    from nico import assessment_cpp_project_snapshot as snapshot
    from tests.test_cpp_baseline_execution import Native, source, contract
    from tests.test_cpp_project_snapshot import _empty_native_snapshot
    from tests.test_cpp_project_static import _simple_compiler_native
    assert 'extended_compiler_budget' in inspect.signature(probe.probe_project_configuration).parameters
    source_root, targets = source(tmp_path)
    docker = Native(targets)
    kept = {}
    calls = []
    def command(argv, **kwargs):
        calls.append((argv, kwargs))
        if snapshot.PROJECT_SNAPSHOT_PROGRAM in argv:
            raw = compiler._canonical(_empty_native_snapshot(__import__('json').loads(kwargs['input_bytes'])))
        elif compiler.PROGRAM in argv:
            req = __import__('json').loads(kwargs['input_bytes'])
            assert req['schema'] == 'nico.cpp-project-compiler-request.v2'
            assert req['limits'] == {'wall_seconds':600, 'case_seconds':90, 'parallel':4}
            assert 600 < kwargs['timeout'] <= 610
            value = _simple_compiler_native(req)
            value['schema'] = 'nico.cpp-project-compiler-evidence.v2'
            raw = compiler._canonical(value)
        else:
            return docker(argv, **kwargs)
        return dict(exit_code=0, timed_out=False, output_truncated=False, output=raw)
    def sink(key, raw):
        kept[key] = raw
        return dict(path='artifacts/'+key+'-'+compiler._digest(raw)+'.json',
                    sha256=compiler._digest(raw), bytes=len(raw))
    result = probe.probe_project_configuration(source_root, targets, 'sha256:'+'a'*64,
        project_options={'BUILD_TESTS':'ON'}, baseline_execution=contract(),
        capture_generated_context=True, project_compiler_evidence=True,
        extended_compiler_budget=True, retain_artifact=sink, command=command)
    assert result['status'] == 'BASELINE_EXECUTED'
    assert result['execution_budget_seconds'] == 1800
    assert result['wall_budget_seconds'] == 1810
    assert result['compiled'] and result['tests_passed'] and result['cleanup_verified']
    assert result['project_compiler']['complete']
    assert not result['full_project_qualified']
    create = next(a for a,k in calls if a[1] == 'create')
    for flag in ('--memory=12g','--memory-swap=12g','--cpus=4','--pids-limit=256','--network=none'):
        assert flag in create


def test_extended_probe_requires_compiler_evidence_and_strict_boolean(tmp_path):
    from nico import assessment_cpp_configuration_probe as probe
    assert 'extended_compiler_budget' in inspect.signature(probe.probe_project_configuration).parameters
    for value in (True, 1, None, 'true'):
        with pytest.raises(ValueError):
            probe.probe_project_configuration(tmp_path, {'CMakeLists.txt':'a'*64}, 'sha256:'+'a'*64,
                project_options={}, extended_compiler_budget=value)


def test_existing_native_workflow_enables_new_budget_for_owned_and_large_controls():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[1]
    path = root / '.github/workflows/cpp-full-project-integration.yml'
    workflow = yaml.safe_load(path.read_text())
    owned = workflow['jobs']['owned-project-integration']
    large = workflow['jobs']['project-baseline-qualification']
    def command(job, marker):
        return next(s['run'] for s in job['steps'] if marker in s.get('run', ''))
    assert '--extended-compiler-budget' in command(owned, 'qualify_cpp_project_generated_context')
    assert '--extended-compiler-budget' in command(large, 'qualify_cpp_project_configuration')
    assert large['timeout-minutes'] == 50
    assert large['needs'] == ['owned-project-integration']
    assert 'tests/test_cpp_project_compiler_budget.py' in path.read_text()
