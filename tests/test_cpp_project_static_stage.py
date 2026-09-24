"""Static staging reuses verified bytes; synthetic Docker calls are not native proof."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from nico import assessment_cpp_project_snapshot as snapshot
from nico import assessment_cpp_full_project_execution as execution
from tests.test_cpp_project_compiler import inputs
from tests.test_cpp_configuration_qualification import boundary


def restore_api():
    value = getattr(snapshot, 'restore_project_files', None)
    assert callable(value), 'missing byte-verified snapshot restoration for separate static stage'
    return value


def restore_request(tmp_path):
    _, _, captured, _ = inputs(tmp_path)
    return {'schema': 'nico.cpp-project-restore.v1', 'files': captured['files'],
            'file_population_sha256': captured['file_population_sha256']}


def test_snapshot_restore_is_exact_read_only_and_all_or_nothing(tmp_path):
    request = restore_request(tmp_path)
    private = tmp_path / 'static-private'; private.mkdir(mode=0o700)
    destination = private / 'generated-baseline'
    result = restore_api()(request, destination)
    assert result['file_population_sha256'] == request['file_population_sha256']
    assert set(result['files']) == set(request['files'])
    assert destination.stat().st_mode & 0o777 == 0o555
    for path, member in request['files'].items():
        leaf = destination / path
        assert leaf.read_bytes() == base64.b64decode(member['base64'])
        assert leaf.stat().st_mode & 0o777 == 0o444
        assert result['files'][path] == {'sha256': member['sha256'], 'bytes': member['bytes']}
    assert not list(private.glob('.project-restore-*'))
    with pytest.raises(ValueError):
        restore_api()(request, destination)


@pytest.mark.parametrize('fault', ['digest', 'size', 'aggregate', 'population', 'traversal', 'prefix', 'parent-link'])
def test_restore_rejects_changed_or_unsafe_inputs_without_partial_publication(tmp_path, monkeypatch, fault):
    request = restore_request(tmp_path)
    private = tmp_path / 'static-private'; private.mkdir(mode=0o700)
    destination = private / 'generated-baseline'
    if fault == 'digest': request['files']['generated/config.h']['sha256'] = '0' * 64
    if fault == 'size': request['files']['generated/config.h']['bytes'] += 1
    if fault == 'aggregate': monkeypatch.setattr(snapshot, 'PROJECT_GENERATED_MAX_BYTES', 1)
    if fault == 'population': request['file_population_sha256'] = '0' * 64
    if fault == 'traversal': request['files']['../escaped.h'] = request['files'].pop('generated/config.h')
    if fault == 'prefix': request['files']['generated'] = request['files']['generated/config.h']
    if fault == 'parent-link':
        linked = tmp_path / 'linked'; linked.symlink_to(private, target_is_directory=True)
        destination = linked / 'generated-baseline'
    with pytest.raises((ValueError, OSError)):
        restore_api()(request, destination)
    assert not destination.exists()
    assert not list(private.glob('.project-restore-*'))
    assert not (tmp_path / 'escaped.h').exists()


def test_static_boundary_requires_noexec_without_changing_executable_baseline():
    import inspect
    assert 'executable' in inspect.signature(execution.boundary_valid).parameters, 'missing explicit static noexec boundary'
    value = boundary(); value.update(cpu_max='400000 100000', memory_max='12884901888')
    profile = 'cpp-baseline-qualification-v1'
    assert execution.boundary_valid(value, profile=profile)
    assert not execution.boundary_valid(value, profile=profile, executable=False)
    value['work_mount'].append('noexec')
    assert not execution.boundary_valid(value, profile=profile)
    assert execution.boundary_valid(value, profile=profile, executable=False)
    assert not execution.boundary_valid(value, profile=profile, executable=0)


def stage_inputs(tmp_path):
    from nico.assessment_cpp_project_compiler import project_compiler_request, _canonical
    from tests.test_cpp_project_compiler import result_for
    database, targets, captured, _ = inputs(tmp_path)
    root = tmp_path / 'source'; root.mkdir()
    (root / 'main.cpp').write_bytes(b'#include "config.h"\nint main(){return VALUE;}\n')
    (root / 'original.h').write_bytes(b'#define ORIGINAL 1\n')
    raw = _canonical(result_for(project_compiler_request(database, targets, captured)))
    return root, targets, database, captured, raw


class StaticDocker:
    def __init__(self, targets, fault=None):
        self.targets, self.fault, self.calls = targets, fault, []

    def __call__(self, argv, **kwargs):
        from nico import assessment_cpp_project_static as analysis
        from nico.assessment_cpp_configuration_probe import SCRATCH_PROGRAM
        from tests.test_cpp_project_static import native
        self.calls.append((argv, kwargs))
        assert argv[0] == 'docker', 'the controller must never execute assessed code'
        raw, code = b'', 0
        if argv[:3] == ['docker', 'image', 'inspect']:
            raw = json.dumps([{'Id': 'sha256:' + ('b' if self.fault == 'image' else 'a') * 64}]).encode()
        elif execution.ANALYSIS_SETUP_PROGRAM in argv:
            raw = b'{"uid":1001,"gid":1001,"private":true}'
        elif execution.BOUNDARY_PROGRAM in argv:
            value = boundary(); value.update(cpu_max='400000 100000', memory_max='12884901888')
            if self.fault != 'noexec': value['work_mount'].append('noexec')
            if self.fault == 'network': value['external_network_blocked'] = False
            raw = json.dumps(value).encode()
        elif execution.INPUT_PROGRAM in argv:
            raw = json.dumps(self.targets).encode()
        elif SCRATCH_PROGRAM in argv:
            raw = b'{"capacity_bytes":9663676416,"available_bytes":9663676416}'
        elif getattr(snapshot, 'PROJECT_RESTORE_PROGRAM', None) in argv:
            request = json.loads(kwargs['input_bytes'])
            result = {'file_population_sha256': request['file_population_sha256'],
                      'files': {p: {k: v[k] for k in ('sha256', 'bytes')} for p, v in request['files'].items()}}
            if self.fault == 'restore': result['file_population_sha256'] = '0' * 64
            raw = json.dumps(result).encode()
        elif analysis.PROGRAM in argv:
            result = native(json.loads(kwargs['input_bytes']), 'uninitvar')
            if self.fault == 'partial': result['records'][0]['execution']['exit_code'] = 1
            if self.fault == 'request': result['request_sha256'] = '0' * 64
            raw = json.dumps(result).encode()
            if self.fault == 'exit': code = 1
        elif argv[-2:] == ['cat', '/sys/fs/cgroup/memory.peak']:
            raw = b'12345678\n'
        elif argv[1:3] == ['rm', '--force'] and self.fault == 'cleanup':
            code = 1
        return {'exit_code': code, 'timed_out': self.fault == 'timeout' and analysis.PROGRAM in argv,
                'output_truncated': self.fault == 'truncated' and analysis.PROGRAM in argv, 'output': raw}


def run_stage(tmp_path, fault=None):
    from nico import assessment_cpp_project_static as analysis
    from scripts.qualify_cpp_project_configuration import persist_project_artifact
    method = getattr(analysis, 'run_project_static_stage', None)
    assert callable(method), 'missing independently bounded static executor'
    root, targets, database, captured, compiler_raw = stage_inputs(tmp_path)
    docker = StaticDocker(targets, fault)
    output = tmp_path / 'evidence'; output.mkdir()
    saved, checkpoints = [], []
    def sink(key, raw):
        if fault == 'sink': raise OSError('owned retention failure')
        return persist_project_artifact(output, key, raw)
    result = method(root, targets, 'sha256:' + 'a' * 64, database, captured, compiler_raw,
                    command=docker, retain=lambda r: saved.append(deepcopy(r)),
                    retain_artifact=sink, checkpoint=lambda: checkpoints.append(True))
    return result, docker, saved, checkpoints, output


def test_static_execution_has_a_fresh_enforced_budget_and_no_executable_workspace(tmp_path):
    result, docker, saved, checkpoints, output = run_stage(tmp_path)
    assert result['complete'] and result['status'] == 'STATIC_ANALYSIS_EXECUTED'
    assert result['boundary_verified'] and result['cleanup_verified']
    assert result['analysis']['required_contexts'] == result['analysis']['analyzed_contexts']
    assert len(result['analysis']['analyzed_contexts']) == 3
    assert result['execution_budget_seconds'] == 600 and result['wall_budget_seconds'] == 610
    assert result['memory_peak_bytes'] == 12345678
    assert result['production_qualified'] is False
    assert checkpoints and saved[-1] == result and saved[0]['complete'] is False
    creates = [a for a, k in docker.calls if a[1] == 'create']; assert len(creates) == 1
    create = creates[0]
    for flag in ('--network=none', '--read-only', '--user=1000:1000', '--cpus=4', '--memory=12g',
                 '--memory-swap=12g', '--pids-limit=256', '--cap-drop=ALL', '--security-opt=no-new-privileges'):
        assert flag in create
    assert '--tmpfs=/work:rw,nosuid,nodev,noexec,size=9663676416,mode=1777' in create
    assert not any(a in {'--privileged', '-v', '--mount'} for a in create)
    assert not any('cmake' in a or 'ctest' in a for a, k in docker.calls)
    analysis_ops = [op for op in result['operations'] if op['id'] == 'project-static-evidence']
    assert len(analysis_ops) == 1 and analysis_ops[0]['output'] is None
    reference = result['analysis']['artifact']
    data = (output / reference['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == reference['sha256'] == analysis_ops[0]['output_artifact']['sha256']
    assert result['request_sha256'] and result['snapshot_population_sha256'] and result['compiler_evidence_sha256']


@pytest.mark.parametrize('fault', ['image', 'noexec', 'network', 'restore', 'exit', 'timeout', 'truncated',
                                 'partial', 'request', 'cleanup', 'sink'])
def test_failed_stage_retains_evidence_but_cannot_complete(tmp_path, fault):
    result, docker, saved, checkpoints, output = run_stage(tmp_path, fault)
    assert result['complete'] is False and result['status'] == 'UNPROVEN'
    assert result['error'] and result['production_qualified'] is False
    assert saved[-1] == result
    if fault in {'image', 'noexec', 'network', 'restore'}:
        assert not any(op['id'] == 'project-static-evidence' for op in result['operations'])
    elif fault == 'partial':
        assert len(result['analysis']['analyzed_contexts']) == 2
        assert len(result['analysis']['required_contexts']) == 3
    elif fault == 'sink':
        op = next(op for op in result['operations'] if op['id'] == 'project-static-evidence')
        assert op['output_sha256'] and op['output_artifact'] is None
    if fault != 'image':
        assert any(a[1:3] == ['rm', '--force'] for a, k in docker.calls)


def test_source_substitution_is_rejected_before_static_container_creation(tmp_path):
    from nico import assessment_cpp_project_static as analysis
    method = getattr(analysis, 'run_project_static_stage', None)
    assert callable(method), 'missing independently bounded static executor'
    root, targets, database, captured, compiler_raw = stage_inputs(tmp_path)
    (root / 'main.cpp').write_text('changed source')
    docker = StaticDocker(targets)
    result = method(root, targets, 'sha256:'+'a'*64, database, captured, compiler_raw,
                    command=docker, retain_artifact=lambda key, raw: None)
    assert result['complete'] is False and result['status'] == 'UNPROVEN'
    assert not any(a[1] == 'create' for a, k in docker.calls)

@pytest.mark.parametrize('fault', [None, 'baseline-cleanup', 'static-incomplete'])
def test_probe_delegates_static_only_after_baseline_cleanup_with_separate_budget(tmp_path, monkeypatch, fault):
    from nico import assessment_cpp_configuration_probe as probe
    from nico import assessment_cpp_project_compiler as compiler
    from nico import assessment_cpp_project_static as analysis
    from tests.test_cpp_baseline_execution import Native, source, contract
    from tests.test_cpp_project_snapshot import _empty_native_snapshot
    from tests.test_cpp_project_static import _simple_compiler_native
    from nico.assessment_cpp_project_compiler import _canonical
    root, targets = source(tmp_path)
    baseline = Native(targets)
    calls, saved, stage_calls = [], [], []
    def command(argv, **kwargs):
        calls.append(argv)
        if snapshot.PROJECT_SNAPSHOT_PROGRAM in argv:
            raw = _canonical(_empty_native_snapshot(json.loads(kwargs['input_bytes'])))
        elif compiler.PROGRAM in argv:
            raw = _canonical(_simple_compiler_native(json.loads(kwargs['input_bytes'])))
        elif argv[1:3] == ['rm', '--force'] and fault == 'baseline-cleanup':
            return dict(exit_code=1, timed_out=False, output_truncated=False, output=b'')
        else:
            return baseline(argv, **kwargs)
        return dict(exit_code=0, timed_out=False, output_truncated=False, output=raw)
    def stage(source_path, received_targets, image, database, captured, compiler_raw, **kwargs):
        assert calls[-1][1:3] == ['rm', '--force']
        assert source_path == root and received_targets == targets
        assert image == 'sha256:'+'a'*64
        assert json.loads(database) and compiler_raw and captured['files'] == {}
        stage_calls.append(True)
        record = dict(complete=fault != 'static-incomplete', execution_budget_seconds=600,
                      analysis={'complete':fault != 'static-incomplete', 'findings':[]},
                      error='worker_project_static_stage_analysis_incomplete' if fault else None)
        kwargs['retain'](record)
        return record
    monkeypatch.setattr(analysis, 'run_project_static_stage', stage)
    def sink(key, raw):
        sha = hashlib.sha256(raw).hexdigest()
        return dict(path='artifacts/'+key+'-'+sha+'.json', sha256=sha, bytes=len(raw))
    result = probe.probe_project_configuration(root, targets, 'sha256:'+'a'*64,
        project_options={'BUILD_TESTS':'ON'}, baseline_execution=contract(), command=command,
        capture_generated_context=True, project_compiler_evidence=True, project_static_analysis=True,
        retain_artifact=sink, retain=lambda value: saved.append(deepcopy(value)))
    assert result['execution_budget_seconds'] == 1800
    assert result['wall_budget_seconds'] == 1810
    assert result['compiled'] and result['tests_passed'] and result['project_compiler']['complete']
    if fault == 'baseline-cleanup':
        assert not stage_calls
        assert result['status'] == 'UNPROVEN'
    else:
        assert stage_calls == [True], 'static analysis must run in a fresh sandbox after baseline cleanup'
        assert result['aggregate_execution_budget_seconds'] == 2400
        assert result['aggregate_wall_budget_seconds'] == 2420
        assert result['aggregate_duration_ms'] >= result['duration_ms']
        assert result['project_static_stage']['execution_budget_seconds'] == 600
        assert result['status'] == ('UNPROVEN' if fault else 'BASELINE_EXECUTED')
    assert saved[-1] == result


@pytest.mark.parametrize('boundary', ['native-return', 'artifact-retention', 'validation'])
@pytest.mark.parametrize('elapsed', [599, 600, 601])
def test_static_stage_deadline_includes_final_output_retention_and_validation(
        tmp_path, monkeypatch, boundary, elapsed):
    """Returned bytes survive a deadline; late evidence never qualifies a stage."""
    from nico import assessment_cpp_project_static as analysis
    from scripts.qualify_cpp_project_configuration import persist_project_artifact
    root, targets, database, captured, compiler_raw = stage_inputs(tmp_path)
    docker = StaticDocker(targets)
    clock = [0.0]
    monkeypatch.setattr(analysis.time, 'monotonic', lambda: clock[0])
    output = tmp_path / 'evidence'; output.mkdir()
    saved = []
    real_validate = analysis.validate_project_static

    def command(argv, **kwargs):
        result = docker(argv, **kwargs)
        if analysis.PROGRAM in argv and boundary == 'native-return':
            clock[0] = float(elapsed)
        return result

    def sink(key, raw):
        result = persist_project_artifact(output, key, raw)
        if boundary == 'artifact-retention':
            clock[0] = float(elapsed)
        return result

    def validate(raw, request):
        result = real_validate(raw, request)
        if boundary == 'validation':
            clock[0] = float(elapsed)
        return result

    monkeypatch.setattr(analysis, 'validate_project_static', validate)
    result = analysis.run_project_static_stage(root, targets, 'sha256:' + 'a' * 64,
        database, captured, compiler_raw, command=command, retain_artifact=sink,
        retain=lambda value: saved.append(deepcopy(value)))
    operation = next(op for op in result['operations'] if op['id'] == 'project-static-evidence')
    reference = operation['output_artifact']
    raw = (output / reference['path']).read_bytes()
    assert len(raw) == reference['bytes']
    assert hashlib.sha256(raw).hexdigest() == reference['sha256'] == operation['output_sha256']
    assert result['cleanup_verified'] and saved[-1] == result
    assert result['duration_ms'] == elapsed * 1000
    if elapsed < 600:
        assert result['complete'] and result['status'] == 'STATIC_ANALYSIS_EXECUTED'
        assert result['error'] is None
    else:
        assert result['complete'] is False and result['status'] == 'UNPROVEN'
        assert result['error'] == 'worker_project_static_stage_deadline'
