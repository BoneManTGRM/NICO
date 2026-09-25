"""Original/generated contexts must consume immutable bytes, not a file count."""
from copy import deepcopy
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from nico import assessment_cpp_project_snapshot as generated
from nico.assessment_cpp_full_project import compilation_contexts


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def capability(name):
    value = getattr(generated, name, None)
    assert callable(value), 'missing project generated-byte capture: ' + name
    return value


def contexts():
    rows = [
        {'directory': '/work/build', 'file': '/work/source/main.cpp',
         'arguments': ['/usr/local/bin/g++', '-DVALUE=1', '-c', '/work/source/main.cpp', '-o', 'first.o']},
        {'directory': '/work/build', 'file': '/work/source/main.cpp',
         'arguments': ['/usr/local/bin/g++', '-DVALUE=2', '-c', '/work/source/main.cpp', '-o', 'second.o']},
        {'directory': '/work/build/generated', 'file': '/work/build/generated/message.capnp.c++',
         'arguments': ['/usr/local/bin/g++', '-c', '/work/build/generated/message.capnp.c++', '-o', 'generated.o']},
    ]
    return compilation_contexts(json.dumps(rows).encode(), {'main.cpp': digest(b'int main(){}')}, '/work/build')


def layout(tmp_path):
    build = tmp_path / 'build'; build.mkdir()
    (build / 'generated').mkdir()
    (build / 'generated/message.capnp.c++').write_bytes(b'#include "config.h"\nint generated(){return VALUE;}\n')
    (build / 'generated/config.h').write_bytes(b'#define VALUE 42\n')
    (build / 'generated/helper.ipp').write_bytes(b'// template implementation\n')
    (build / 'unrelated.o').write_bytes(b'not source')
    private = tmp_path / 'private'; private.mkdir(mode=0o700)
    return build, private / 'generated-baseline'


def capture(tmp_path):
    build, destination = layout(tmp_path)
    request = capability('project_snapshot_request')(contexts())
    value = capability('capture_project_snapshot')(build, destination, request)
    return build, destination, request, value


def test_generated_source_and_headers_are_copied_with_exact_context_binding(tmp_path):
    build, destination, request, value = capture(tmp_path)
    assert value['schema'] == 'nico.cpp-generated-project.v1'
    assert value['generated_units'] == ['generated/message.capnp.c++']
    assert value['header_candidates'] == ['generated/config.h', 'generated/helper.ipp']
    assert set(value['files']) == {'generated/message.capnp.c++', 'generated/config.h', 'generated/helper.ipp'}
    assert value['context_membership_sha256'] == contexts()['context_membership_sha256']
    assert value['database_sha256'] == contexts()['database_sha256']
    assert value['source_population_sha256'] == contexts()['source_population_sha256']
    assert value['analysis_executed'] is False and value['header_dependencies_verified'] is False
    assert value['captured_bytes'] == sum(v['bytes'] for v in value['files'].values())
    for name, item in value['files'].items():
        original = (build / name).read_bytes()
        assert base64.b64decode(item['base64'], validate=True) == original
        assert item['sha256'] == digest(original)
        assert (destination / name).read_bytes() == original
        assert (destination / name).stat().st_mode & 0o777 == 0o444
    assert destination.stat().st_mode & 0o777 == 0o555
    assert not (destination / 'unrelated.o').exists()
    (build / 'generated/config.h').write_bytes(b'#define VALUE 99\n')
    assert (destination / 'generated/config.h').read_bytes() == b'#define VALUE 42\n'
    assert capability('validate_project_snapshot')(value, contexts()) == value


@pytest.mark.parametrize('fault', ['missing', 'symlink-file', 'symlink-parent', 'hardlink', 'fifo'])
def test_required_generated_inputs_cannot_be_substituted(tmp_path, fault):
    build, destination = layout(tmp_path)
    leaf = build / 'generated/message.capnp.c++'
    if fault == 'missing': leaf.unlink()
    elif fault == 'symlink-file':
        leaf.unlink(); leaf.symlink_to(build / 'generated/config.h')
    elif fault == 'hardlink':
        os.link(leaf, build / 'alias.c++')
    elif fault == 'fifo':
        leaf.unlink(); os.mkfifo(leaf)
    else:
        (build / 'generated').rename(build / 'original')
        (build / 'generated').symlink_to(build / 'original', target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        capability('capture_project_snapshot')(build, destination, capability('project_snapshot_request')(contexts()))
    assert not destination.exists()
    assert not list(destination.parent.glob('.project-generated-*'))


def test_header_symlink_is_not_reported_as_captured(tmp_path):
    build, destination = layout(tmp_path)
    (build / 'alias.h').symlink_to(build / 'generated/config.h')
    with pytest.raises((ValueError, OSError)):
        capability('capture_project_snapshot')(build, destination, capability('project_snapshot_request')(contexts()))
    assert not destination.exists()


@pytest.mark.parametrize('fault', ['writable-parent', 'existing-destination', 'linked-parent'])
def test_snapshot_destination_must_be_private_and_new(tmp_path, fault):
    build, destination = layout(tmp_path)
    if fault == 'writable-parent': destination.parent.chmod(0o777)
    elif fault == 'existing-destination': destination.mkdir()
    else:
        alias = tmp_path / 'alias'; alias.symlink_to(destination.parent, target_is_directory=True)
        destination = alias / destination.name
    with pytest.raises((ValueError, OSError)):
        capability('capture_project_snapshot')(build, destination, capability('project_snapshot_request')(contexts()))


def test_changed_generated_bytes_abort_before_publication(tmp_path, monkeypatch):
    build, destination = layout(tmp_path)
    original = generated._stable_bytes
    seen = {}
    def changing(root, relative, maximum):
        value = original(root, relative, maximum)
        seen[relative] = seen.get(relative, 0) + 1
        return value + b'changed' if seen[relative] > 1 else value
    monkeypatch.setattr(generated, '_stable_bytes', changing)
    with pytest.raises(ValueError, match='changed'):
        capability('capture_project_snapshot')(build, destination, capability('project_snapshot_request')(contexts()))
    assert not destination.exists()


@pytest.mark.parametrize('fault', ['digest', 'bytes', 'base64', 'missing-unit', 'extra-field', 'visited-claim', 'database', 'membership', 'population'])
def test_host_reconstructs_snapshot_identity_and_never_accepts_false_coverage(tmp_path, fault):
    _, _, _, original = capture(tmp_path)
    value = deepcopy(original)
    item = value['files']['generated/config.h']
    if fault == 'digest': item['sha256'] = '0' * 64
    elif fault == 'bytes': item['bytes'] = True
    elif fault == 'base64': item['base64'] = '!!!'
    elif fault == 'missing-unit': del value['files']['generated/message.capnp.c++']
    elif fault == 'extra-field': value['approved'] = True
    elif fault == 'visited-claim': value['header_dependencies_verified'] = True
    elif fault == 'database': value['database_sha256'] = '0' * 64
    elif fault == 'membership': value['context_membership_sha256'] = '0' * 64
    elif fault == 'population': value['source_population_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        capability('validate_project_snapshot')(value, contexts())


def test_snapshot_size_failure_is_not_a_partial_success(tmp_path, monkeypatch):
    build, destination = layout(tmp_path)
    monkeypatch.setattr(generated, 'PROJECT_GENERATED_MAX_BYTES', 12, raising=False)
    with pytest.raises(ValueError):
        capability('capture_project_snapshot')(build, destination, capability('project_snapshot_request')(contexts()))
    assert not destination.exists()


def test_same_relative_original_and_generated_paths_remain_separate():
    source = contexts()
    request = capability('project_snapshot_request')(source)
    assert request['generated_units'] == source['generated_units']
    assert 'main.cpp' not in request['generated_units']
    assert source['context_count'] == 3
    assert len(source['original_units']) == 1


def test_no_generated_files_is_valid_but_does_not_prove_header_execution(tmp_path):
    build = tmp_path / 'build'; build.mkdir()
    private = tmp_path / 'private'; private.mkdir(mode=0o700)
    rows = [{'directory': '/work/build', 'file': '/work/source/main.cpp',
             'arguments': ['/usr/local/bin/g++', '-c', '/work/source/main.cpp', '-o', 'main.o']}]
    c = compilation_contexts(json.dumps(rows).encode(), {'main.cpp': digest(b'int main(){}')}, '/work/build')
    request = capability('project_snapshot_request')(c)
    value = capability('capture_project_snapshot')(build, private / 'snapshot', request)
    assert value['files'] == {} and value['captured_bytes'] == 0
    assert value['header_dependencies_verified'] is False
    assert capability('validate_project_snapshot')(value, c) == value


def _empty_native_snapshot(request):
    return {**request, 'schema': 'nico.cpp-generated-project.v1', 'header_candidates': [],
        'unfollowed_links': [], 'files': {}, 'captured_bytes': 0,
        'file_population_sha256': digest(b'{}'), 'analysis_executed': False,
        'header_dependencies_verified': False}


def _probe(tmp_path, fault=None):
    import inspect
    from nico import assessment_cpp_configuration_probe as probe
    from tests.test_cpp_baseline_execution import Native, source, contract
    assert 'capture_generated_context' in inspect.signature(probe.probe_project_configuration).parameters, 'missing native snapshot integration'
    root, targets = source(tmp_path)
    native = Native(targets)
    captured, retained = {}, []
    def command(argv, **kwargs):
        if generated.PROJECT_SNAPSHOT_PROGRAM in argv:
            native.calls.append((argv, kwargs))
            request = json.loads(kwargs['input_bytes'])
            value = _empty_native_snapshot(request)
            if fault == 'identity': value['database_sha256'] = '0' * 64
            return {'exit_code': 1 if fault == 'exit' else 0,
                'timed_out': fault == 'timeout', 'output_truncated': fault == 'truncated',
                'output': json.dumps(value).encode()}
        return native(argv, **kwargs)
    def sink(key, raw):
        captured[key] = raw
        if fault == 'sink': raise OSError('synthetic storage unavailable')
        return {'path': 'artifacts/' + key + '-' + digest(raw) + '.json',
                'bytes': len(raw), 'sha256': digest(raw)}
    result = probe.probe_project_configuration(root, targets, 'sha256:' + 'a' * 64,
        project_options={'BUILD_TESTS': 'ON'}, baseline_execution=contract(), command=command,
        capture_generated_context=True, retain_artifact=sink,
        retain=lambda r: retained.append(deepcopy(r)))
    return result, native, captured, retained


def test_native_capture_runs_as_private_analyst_and_retains_separate_artifact(tmp_path):
    result, native, captured, retained = _probe(tmp_path)
    assert result['status'] == 'BASELINE_EXECUTED'
    assert result['schema'] == 'nico.cpp-project-configuration-probe.v4'
    assert result['generated_context_verified'] is True
    assert result['tests_passed'] is True and result['full_project_qualified'] is False
    row = next(op for op in result['operations'] if op['id'] == 'project-generated-context')
    assert row['output'] is None
    raw = captured['project-generated-context']
    assert row['output_artifact']['sha256'] == digest(raw)
    assert row['output_artifact']['bytes'] == len(raw)
    assert result['generated_context']['artifact'] == row['output_artifact']
    assert 'base64' not in json.dumps(result['generated_context'])
    command = next(a for a, k in native.calls if generated.PROJECT_SNAPSHOT_PROGRAM in a)
    assert '--user=1001:1001' in command and '-I' in command and '-S' in command
    ids = [op['id'] for op in result['operations']]
    assert ids.index('baseline-junit') < ids.index('project-generated-context')
    assert retained[-1] == result


@pytest.mark.parametrize('fault', ['exit', 'timeout', 'truncated', 'identity', 'sink'])
def test_capture_failure_retains_passed_baseline_without_claiming_capture(tmp_path, fault):
    result, native, captured, retained = _probe(tmp_path, fault)
    assert result['status'] == 'UNPROVEN'
    assert result['compiled'] is True and result['tests_passed'] is True
    assert result['generated_context_verified'] is False
    assert result['full_project_qualified'] is False and result['cleanup_verified'] is True
    assert captured['project-generated-context']
    assert retained[-1] == result


def test_opt_in_snapshot_requires_a_baseline_and_artifact_sink_before_execution(tmp_path):
    import inspect
    from nico import assessment_cpp_configuration_probe as probe
    from tests.test_cpp_baseline_execution import source, Native, contract
    assert 'capture_generated_context' in inspect.signature(probe.probe_project_configuration).parameters, 'missing native snapshot integration'
    root, targets = source(tmp_path); native = Native(targets)
    for options in ({}, {'baseline_execution': contract()}, {'retain_artifact': lambda *a: None}):
        with pytest.raises(ValueError):
            probe.probe_project_configuration(root, targets, 'sha256:' + 'a' * 64,
                project_options={}, command=native, capture_generated_context=True, **options)
    assert native.calls == []


def test_artifact_sink_is_digest_bound_atomic_and_does_not_change_old_receipts(tmp_path):
    from scripts import qualify_cpp_project_configuration as script
    function = getattr(script, 'persist_project_artifact', None)
    assert callable(function), 'missing external snapshot artifact retention'
    raw = b'{"synthetic":"snapshot"}'
    ref = function(tmp_path, 'project-generated-context', raw)
    assert ref == {'path': 'artifacts/project-generated-context-' + digest(raw) + '.json',
                   'sha256': digest(raw), 'bytes': len(raw)}
    assert (tmp_path / ref['path']).read_bytes() == raw
    assert function(tmp_path, 'project-generated-context', raw) == ref
    (tmp_path / ref['path']).write_bytes(b'corrupt')
    with pytest.raises(ValueError): function(tmp_path, 'project-generated-context', raw)
    with pytest.raises(ValueError): function(tmp_path, '../receipt', raw)
    assert not (tmp_path / 'receipt.json').exists()
    assert not list((tmp_path / 'artifacts').glob('*.tmp'))


def test_owned_native_control_and_large_snapshot_are_wired_without_new_permissions():
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/cpp-full-project-integration.yml').read_text())
    control = workflow['jobs']['owned-project-integration']
    baseline = workflow['jobs']['project-baseline-qualification']
    text = json.dumps(control)
    assert 'scripts.qualify_cpp_project_generated_context' in text, 'missing real owned snapshot control'
    assert '--capture-generated-context' in json.dumps(baseline), 'missing frozen Bitcoin snapshot execution'
    assert control['timeout-minutes'] == 10 and baseline['timeout-minutes'] == 155
    assert baseline['needs'] == ['owned-project-integration']
    assert workflow['permissions'] == {'contents': 'read'}
    assert 'tests/test_cpp_project_snapshot.py' in json.dumps(workflow['jobs']['contract-regressions'])


def test_owned_snapshot_control_entrypoint_exists_and_covers_both_outcomes():
    root = Path(__file__).resolve().parents[1]
    path = root / 'scripts/qualify_cpp_project_generated_context.py'
    assert path.is_file(), 'missing executable native control entrypoint'
    from scripts.qualify_cpp_project_generated_context import fixture
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        first = Path(tmp) / 'positive'; second = Path(tmp) / 'negative'
        a, b = fixture(first), fixture(second, True)
        assert a.keys() == b.keys()
        assert a['repeated.cpp'] == b['repeated.cpp']
        assert 'VARIANT=1' in (first / 'CMakeLists.txt').read_text()
        assert 'VARIANT=2' in (first / 'CMakeLists.txt').read_text()
        assert 'rejected.h' not in (first / 'CMakeLists.txt').read_text()
        assert 'rejected.h' in (second / 'CMakeLists.txt').read_text()


@pytest.mark.parametrize('fault', ['missing-unit', 'missing-context', 'membership', 'duplicate-context'])
def test_snapshot_request_cannot_drop_a_required_context_or_generated_unit(fault):
    value = contexts()
    if fault == 'missing-unit': value['generated_units'] = []
    elif fault == 'missing-context': value['contexts'].pop()
    elif fault == 'membership': value['context_membership_sha256'] = '0' * 64
    else: value['contexts'][1]['context_id'] = value['contexts'][0]['context_id']
    with pytest.raises(ValueError):
        capability('project_snapshot_request')(value)
