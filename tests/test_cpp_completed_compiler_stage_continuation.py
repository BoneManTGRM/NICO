"""Owned transport controls for independent collection after a real target error.

These are control-flow regressions; actual compiler execution is separately
bound to retained primary evidence and is never inferred from this transport.
"""
import base64
from copy import deepcopy
import hashlib
import inspect
import json

import pytest

from nico import assessment_cpp_configuration_probe as probe
from nico import assessment_cpp_project_compiler as compiler
from nico import assessment_cpp_project_snapshot as snapshot
from tests.test_cpp_baseline_execution import Native, source, contract, DB
from tests.test_cpp_runtime_execution import plan


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def owned_probe(tmp_path, monkeypatch, stage, fault=None, policy=True, *, static_raises=False):
    root, targets = source(tmp_path)
    database = [*deepcopy(DB), {'directory': '/work/build',
        'file': '/work/build/owned_failure.cpp', 'arguments': ['/usr/local/bin/g++',
        '-std=c++20', '-c', '/work/build/owned_failure.cpp', '-o', 'failure.o']}]
    rawdb = json.dumps(database).encode()
    spec = contract(); spec['compilation_database_sha256'] = sha(rawdb)
    build = tmp_path / 'generated'; build.mkdir()
    (build / 'owned_failure.cpp').write_bytes(b'#error owned generated failure\n')
    analyst = tmp_path / 'analyst'; analyst.mkdir(mode=0o700)
    native = Native(targets); retained = {}; calls = []

    def command(argv, **kwargs):
        if probe.READ_PROGRAM in argv and '/work/build/compile_commands.json' in argv:
            native.calls.append((argv, kwargs))
            raw = json.dumps({'data': base64.b64encode(rawdb).decode(), 'truncated': False}).encode()
        elif snapshot.PROJECT_SNAPSHOT_PROGRAM in argv:
            native.calls.append((argv, kwargs))
            captured = snapshot.capture_project_snapshot(build, analyst / 'generated-baseline',
                json.loads(kwargs['input_bytes']))
            raw = compiler._canonical(captured)
        elif compiler.PROGRAM in argv:
            native.calls.append((argv, kwargs)); request = json.loads(kwargs['input_bytes']); records = []
            for context in request['contexts']:
                generated = context['origin'] == 'generated'
                output = ((context['analysis_file'] + ':1:2: error: #error owned generated failure\n'
                    '    1 | #error owned generated failure\n      |  ^~~~~\n').encode() if generated else b'')
                deps = b'' if generated else ('nico_unit: ' + context['analysis_file'] + '\n').encode()
                records.append({'context_id': context['context_id'], 'invocation': context['invocation'],
                    'execution': {'exit_code': 1 if generated else 0, 'timed_out': False,
                        'output_truncated': False, 'duration_ms': 1,
                        'output': base64.b64encode(output).decode(), 'output_sha256': sha(output)},
                    'dependency_bytes': base64.b64encode(deps).decode(),
                    'dependency_sha256': sha(deps) if deps else None,
                    'source_dependencies': {} if generated else {context['path']: targets[context['path']]},
                    'generated_dependencies': {}, 'toolchain_dependencies': [], 'error': None})
            failed = records[-1]
            if fault == 'timeout': failed['execution']['timed_out'] = True
            if fault == 'truncated': failed['execution']['output_truncated'] = True
            if fault == 'permission':
                output = b'g++: fatal error: owned input: Permission denied\n'
                failed['execution'].update(output=base64.b64encode(output).decode(), output_sha256=sha(output))
            if fault == 'missing': records.pop()
            raw = compiler._canonical({'schema': 'nico.cpp-project-compiler-evidence.v1',
                'request_sha256': sha(compiler._canonical(request)), 'analyst_uid': 1001,
                'records': records, 'duration_ms': 5})
        else:
            return native(argv, **kwargs)
        return {'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'output': raw}

    def sink(key, raw):
        retained[key] = raw
        return {'path': 'artifacts/' + key + '-' + sha(raw) + '.json', 'sha256': sha(raw), 'bytes': len(raw)}

    def runtime(*args, **kwargs):
        calls.append('runtime')
        # An independently ready stage is reached; no fabricated runtime result.
        raise ValueError('worker_runtime_owned_control_stop')

    def static(*args, **kwargs):
        calls.append('static')
        if static_raises:
            raise ValueError('worker_project_static_stage_owned_control_stop')
        return {'complete': False, 'error': 'worker_project_static_stage_owned_control_stop', 'analysis': None}

    from nico import assessment_cpp_runtime_execution as runtime_module
    from nico import assessment_cpp_project_static as static_module
    monkeypatch.setattr(runtime_module, 'execute_runtime_plan', runtime)
    monkeypatch.setattr(static_module, 'run_project_static_stage', static)
    options = {'project_options': {'BUILD_TESTS': 'ON'}, 'baseline_execution': spec,
        'capture_generated_context': True, 'project_compiler_evidence': True,
        'retain_artifact': sink, 'command': command,
        'runtime_plan': plan() if stage in {'runtime', 'both'} else None,
        'project_static_analysis': stage in {'static', 'both'}}
    # Original behavior fails at the intended skipped-stage assertion, not import
    # or an unsupported keyword. The opt-in never changes legacy callers.
    if 'collect_completed_compiler_failures' in inspect.signature(probe.probe_project_configuration).parameters:
        options['collect_completed_compiler_failures'] = policy
    result = probe.probe_project_configuration(root, targets, 'sha256:' + 'a' * 64, **options)
    return result, calls, retained


@pytest.mark.parametrize('stage', ['runtime', 'static'])
def test_completed_generated_error_reaches_independent_collection(tmp_path, monkeypatch, stage):
    result, calls, retained = owned_probe(tmp_path, monkeypatch, stage)
    assert result['compiled'] and result['tests_passed'] and result['generated_context_verified']
    assert result['project_compiler']['complete'] is False
    assert stage in calls, 'captured target compiler failure stopped independently ready collection'
    assert result['status'] == 'UNPROVEN' and result['full_project_qualified'] is False
    assert 'project-compiler-evidence' in retained
    assert result['project_compiler_collection']['collection_complete'] is True
    assert result['project_compiler_collection']['compiler']['complete'] is False
    assert len(result['project_compiler_collection']['failed_contexts']) == 1


@pytest.mark.parametrize('stage', ['runtime', 'static'])
@pytest.mark.parametrize('fault', ['timeout', 'truncated', 'permission', 'missing'])
def test_incomplete_or_infrastructure_failure_does_not_gain_collection_credit(tmp_path, monkeypatch, stage, fault):
    result, calls, _ = owned_probe(tmp_path, monkeypatch, stage, fault)
    assert calls == []
    assert result['status'] == 'UNPROVEN' and not result['full_project_qualified']
    assert not (result.get('project_compiler_collection') or {}).get('collection_complete')


def test_legacy_policy_preserves_original_fail_closed_behavior(tmp_path, monkeypatch):
    result, calls, _ = owned_probe(tmp_path, monkeypatch, 'runtime', policy=False)
    assert calls == [] and result['project_compiler']['complete'] is False
    assert result['status'] == 'UNPROVEN'


@pytest.mark.parametrize('static_raises', [False, True])
def test_later_static_failure_preserves_first_independent_error(tmp_path, monkeypatch, static_raises):
    runtime_root = tmp_path / 'runtime'; runtime_root.mkdir()
    earlier, earlier_calls, _ = owned_probe(runtime_root, monkeypatch, 'runtime')
    assert earlier_calls == ['runtime']
    assert earlier['independent_collection_error'] == 'worker_configuration_probe_failed'

    combined_root = tmp_path / 'combined'; combined_root.mkdir()
    combined, calls, retained = owned_probe(combined_root, monkeypatch, 'both', static_raises=static_raises)
    assert calls == ['runtime', 'static']
    # No runtime receipt exists for this exception. The singular independent
    # error is the only retained explanation of that earlier failed phase.
    assert combined['runtime_evidence'] is None
    assert combined['independent_collection_error'] == earlier['independent_collection_error']
    assert combined['error'] == earlier['error'] == 'worker_configuration_probe_compiler_incomplete'
    assert combined['status'] == 'UNPROVEN' and combined['full_project_qualified'] is False
    assert combined['project_compiler_collection'] == earlier['project_compiler_collection']
    assert combined['project_compiler']['complete'] is False
    assert 'project-compiler-evidence' in retained


@pytest.mark.parametrize('static_raises', [False, True])
def test_static_failure_without_prior_error_still_records_its_reason(tmp_path, monkeypatch, static_raises):
    result, calls, _ = owned_probe(tmp_path, monkeypatch, 'static', static_raises=static_raises)
    assert calls == ['static']
    expected = 'worker_configuration_probe_static_' + ('failed' if static_raises else 'incomplete')
    assert result['independent_collection_error'] == expected
    assert result['error'] == 'worker_configuration_probe_compiler_incomplete'
    assert result['status'] == 'UNPROVEN' and result['full_project_qualified'] is False
