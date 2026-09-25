"""Generated include contexts: bounded snapshots, never mutable compiler input."""
from copy import deepcopy
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from nico.assessment_cpp_generated_context import (
    MAX_GENERATED_BYTES, MAX_GENERATED_FILE_BYTES, capture_headers,
    validate_header_paths, validate_snapshot, safe_generated_compile_argv,
    derive_database, snapshot_directory,
)

UNIT = '/work/source/main.cpp'
ARGV = ['/usr/local/bin/g++', '-I/work/source', '-I/work/build/include',
        '-DVALUE=2', '-g', '-std=c++20', '-c', UNIT, '-o', 'main.o']
HEADERS = ['include/config.h']


def snapshot(group='baseline', data=b'#define CONFIGURED_VALUE 42\n'):
    return {'schema': 'nico.cpp-generated-context.v1', 'configuration': group,
        'analyst_uid': 1001, 'files': {'include/config.h': {
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'base64': base64.b64encode(data).decode()}}, 'captured_bytes': len(data)}


def test_generated_directory_is_replaced_without_changing_other_flags():
    out = safe_generated_compile_argv(ARGV, UNIT, '/work/analysis/compiler-baseline/u0',
                                     'baseline', HEADERS)
    assert '-I/work/analysis/generated-baseline/include' in out
    assert '-I/work/build/include' not in out
    assert {'-I/work/source', '-DVALUE=2', '-g', '-std=c++20', '-c', UNIT} <= set(out)
    assert out[-7:] == ['-o', '/work/analysis/compiler-baseline/u0.o', '-MD', '-MF',
                       '/work/analysis/compiler-baseline/u0.d', '-MT', 'nico_unit']


@pytest.mark.parametrize('args', [
    ['-I/work/address/include'], ['-I/work/build/unlisted'],
    ['-include', '/work/build/include/missing.h'], ['-I/work/build/../source'],
    ['-I/dev/shm/include'], ['-isystem', '/proc/self'],
    ['-fplugin=/work/source/helper.so'], ['@/work/source/response'],
    ['-B/work/source'], ['-wrapper', '/work/source/helper'],
    ['-E'], ['-x', 'assembler'], ['-I/work/build/include/.'],
])
def test_unfrozen_or_unsafe_compiler_context_is_rejected(args):
    with pytest.raises(ValueError):
        safe_generated_compile_argv(ARGV + args, UNIT, '/work/analysis/compiler-baseline/u0', 'baseline', HEADERS)


@pytest.mark.parametrize('flag', ['-I', '-isystem', '-iquote', '-include', '-imacros'])
def test_separate_include_forms_remap_only_declared_context(flag):
    path = '/work/build/include/config.h' if flag in {'-include', '-imacros'} else '/work/build/include'
    result = safe_generated_compile_argv(ARGV + [flag, path], UNIT,
                                        '/work/analysis/compiler-baseline/u0', 'baseline', HEADERS)
    at = result.index(flag)
    assert result[at + 1] == path.replace('/work/build', '/work/analysis/generated-baseline')


def test_existing_v2_still_rejects_mutable_include_context():
    from nico.assessment_cpp_compiler_evidence import safe_compile_argv
    with pytest.raises(ValueError, match='mutable_include_context'):
        safe_compile_argv(ARGV, UNIT, '/work/analysis/compiler-baseline/u0')


@pytest.mark.parametrize('paths', [[], ['../x.h'], ['/x.h'], ['a//x.h'], ['a/./x.h'],
    ['a/.git/x.h'], ['a/x.so'], ['a/x.h', 'a/x.h'], ['b.h', 'a.h'], 'a.h', [False],
    ['a\\x.h'], ['a/x.h\n'], ['x.h', 'x.h/y.h'], ['x.h'] * 129])
def test_invalid_header_population_is_rejected(paths):
    with pytest.raises(ValueError): validate_header_paths(paths)


def test_snapshot_copies_original_bytes_and_does_not_change_generated_input(tmp_path):
    build = tmp_path / 'build'; build.mkdir()
    (build / 'include').mkdir()
    original = build / 'include/config.h'; original.write_bytes(b'#define VALUE 42\n')
    private = tmp_path / 'private'; private.mkdir(mode=0o700)
    destination = private / 'snapshot'
    files = capture_headers(build, destination, HEADERS)
    assert files['include/config.h']['sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert (destination / 'include/config.h').read_bytes() == original.read_bytes()
    assert (destination / 'include/config.h').stat().st_mode & 0o777 == 0o444
    assert destination.stat().st_mode & 0o777 == 0o555
    original.write_bytes(b'changed after snapshot')
    assert (destination / 'include/config.h').read_bytes() == b'#define VALUE 42\n'


@pytest.mark.parametrize('kind', ['leaf_link', 'directory_link', 'hardlink', 'fifo', 'oversize', 'missing', 'root_link'])
def test_bad_generated_input_never_leaves_a_completed_snapshot(tmp_path, kind):
    build = tmp_path / 'build'; build.mkdir()
    other = tmp_path / 'other'; other.mkdir(); (other / 'config.h').write_bytes(b'owned fixture')
    (build / 'include').mkdir()
    target = build / 'include/config.h'
    if kind == 'leaf_link': target.symlink_to(other / 'config.h')
    elif kind == 'directory_link':
        (build / 'include').rmdir(); (build / 'include').symlink_to(other, target_is_directory=True)
    elif kind == 'hardlink': os.link(other / 'config.h', target)
    elif kind == 'fifo': os.mkfifo(target)
    elif kind == 'oversize': target.write_bytes(b'x' * (MAX_GENERATED_FILE_BYTES + 1))
    elif kind == 'root_link':
        alias = tmp_path / 'alias'; alias.symlink_to(build, target_is_directory=True); build = alias
    private = tmp_path / 'private'; private.mkdir(mode=0o700)
    destination = private / 'snapshot'
    with pytest.raises((ValueError, OSError)): capture_headers(build, destination, HEADERS)
    assert not destination.exists()
    assert list(private.iterdir()) == []


def test_aggregate_bytes_are_bounded_without_silent_truncation(tmp_path):
    build = tmp_path / 'build'; build.mkdir()
    paths = [f'f{i}.h' for i in range(MAX_GENERATED_BYTES // MAX_GENERATED_FILE_BYTES + 1)]
    for p in paths: (build / p).write_bytes(b'x' * MAX_GENERATED_FILE_BYTES)
    private = tmp_path / 'private'; private.mkdir(mode=0o700)
    with pytest.raises(ValueError): capture_headers(build, private / 'snapshot', paths)
    assert list(private.iterdir()) == []


@pytest.mark.parametrize('change', ['uid', 'group', 'hash', 'size', 'total', 'extra', 'missing', 'base64', 'schema', 'boolsize'])
def test_snapshot_binding_is_reconstructed_not_trusted(change):
    value = snapshot(); item = value['files']['include/config.h']
    if change == 'uid': value['analyst_uid'] = 1000
    elif change == 'group': value['configuration'] = 'address'
    elif change == 'hash': item['sha256'] = 'a' * 64
    elif change == 'size': item['bytes'] += 1
    elif change == 'total': value['captured_bytes'] += 1
    elif change == 'extra': value['files']['other.h'] = deepcopy(item)
    elif change == 'missing': value['files'].clear()
    elif change == 'base64': item['base64'] = '#'
    elif change == 'schema': value['schema'] = 'unknown'
    else: item['bytes'] = True
    with pytest.raises(ValueError): validate_snapshot(value, 'baseline', HEADERS)


def test_derived_database_preserves_source_and_binds_frozen_includes():
    raw = json.dumps([{'directory': '/work/build', 'file': UNIT, 'arguments': ARGV}]).encode()
    result = json.loads(derive_database(raw, ['main.cpp'], 'baseline', HEADERS))
    assert result[0]['file'] == UNIT
    assert result[0]['directory'] == '/work/analysis'
    assert '-I/work/analysis/generated-baseline/include' in result[0]['arguments']
    assert json.loads(raw)[0]['directory'] == '/work/build'


def test_generated_configuration_is_opt_in_and_does_not_rewrite_old_profiles():
    from nico.assessment_cpp_full_project import configuration, validate_configuration, execution_steps
    targets = {'CMakeLists.txt': 'a' * 64, 'main.cpp': 'b' * 64}
    old = configuration(units=['main.cpp'], unit_tests=['unit'], integration_tests=['integration'], compiler_evidence=True)
    assert old['schema'] == 'nico.cpp-cmake-configuration.v2'
    new = configuration(units=['main.cpp'], unit_tests=['unit'], integration_tests=['integration'],
                        compiler_evidence=True, generated_headers=HEADERS)
    assert new['schema'] == 'nico.cpp-cmake-configuration.v4'
    validate_configuration(new, targets)
    steps = execution_steps({'configuration': new})
    assert [r['id'] for r in steps if 'generated_configuration' in r] == [
        'baseline-generated-context', 'address-generated-context', 'undefined-generated-context']
    assert 'baseline-generated-context' in next(r for r in steps if r['id'] == 'baseline-compiler-evidence')['needs']


def v3_fixture():
    from tests.test_cpp_compiler_evidence import v2_fixture
    from tests.test_assessment_cpp_full_project import encoded
    from nico.assessment_cpp_full_project import execution_steps
    from nico.assessment_cpp_generated_context import MODE
    p, old = v2_fixture()
    p['configuration'].update(schema='nico.cpp-cmake-configuration.v4', compiler_evidence=MODE,
                              generated_headers=HEADERS, native_test_evidence='not_requested')
    previous = {row['id']: row for row in old['steps']}
    n = deepcopy(old); n['steps'] = []
    for spec in execution_steps(p):
        row = deepcopy(previous.get(spec['id'], {'id': spec['id'], 'attempted': True,
            'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'duration_ms': 1,
            'output': '', 'artifacts': {}}))
        row['invocation'] = spec['invocation']
        n['steps'].append(row)
    for group in ('baseline', 'address', 'undefined'):
        configured = next(row for row in n['steps'] if row['id'] == group + '-configure')
        db = json.loads(base64.b64decode(configured['artifacts']['compilation_database']))
        build = '/work/build' if group == 'baseline' else '/work/' + group
        for row in db: row['arguments'].insert(1, '-I' + build + '/include')
        raw_db = json.dumps(db).encode()
        configured['artifacts']['compilation_database'] = encoded(raw_db)
        value = snapshot(group); raw_context = json.dumps(value).encode()
        context = next(row for row in n['steps'] if row['id'] == group + '-generated-context')
        context['output'] = encoded(raw_context)
        compiler = next(row for row in n['steps'] if row['id'] == group + '-compiler-evidence')
        proof = json.loads(base64.b64decode(compiler['output']))
        derived = derive_database(raw_db, p['configuration']['translation_units'], group, HEADERS)
        proof.update(schema='nico.cpp-direct-compiler.v2', database_sha256=hashlib.sha256(raw_db).hexdigest(),
            analysis_database_sha256=hashlib.sha256(derived).hexdigest(),
            generated_context_sha256=hashlib.sha256(raw_context).hexdigest())
        for record, row in zip(proof['records'], json.loads(derived)):
            record['invocation'] = row['arguments']
            deps = (f"nico_unit: {row['file']} /work/source/sum.hpp "
                    f"{snapshot_directory(group)}/include/config.h /usr/include/stdc-predef.h\n").encode()
            record.update(dependency_bytes=encoded(deps), dependency_sha256=hashlib.sha256(deps).hexdigest(),
                generated_dependencies={'include/config.h': value['files']['include/config.h']['sha256']},
                toolchain_dependencies=['/usr/include/stdc-predef.h'])
        compiler['output'] = encoded(json.dumps(proof).encode())
        if group == 'baseline':
            analysis = next(row for row in n['steps'] if row['id'] == 'static-analysis')
            analysis['artifacts']['compilation_database'] = encoded(derived)
    return p, n


def test_v3_keeps_original_generated_and_image_populations_separate():
    from nico.assessment_cpp_full_project import validate_native
    p, n = v3_fixture(); result = validate_native(n, p)
    assert result['complete'] is True
    assert result['build']['implemented_command_scope_complete'] is True
    assert result['build']['requested_scope_complete'] is False
    assert result['build']['full_project_qualified'] is False
    assert result['build']['compiled_translation_units'] == ['main.cpp', 'sum.cpp']
    proof = result['build']['compiler_evidence']['baseline']
    assert proof['header_inclusions'] == {'sum.hpp': ['main.cpp', 'sum.cpp']}
    assert proof['generated_header_inclusions'] == {'include/config.h': ['main.cpp', 'sum.cpp']}
    assert proof['toolchain_header_paths'] == ['/usr/include/stdc-predef.h']
    assert proof['toolchain_image_digest'] == p['image_digest']
    assert result['build']['generated_context']['baseline']['origin'].endswith('not immutable Git source')
    assert result['coverage']['required_source_headers'] == ['sum.hpp']
    assert result['build']['sanitizers']['address']['instrumentation_verified'] is False
    assert result['build']['fuzz_executed'] is False


@pytest.mark.parametrize('change', ['context_digest', 'database_digest', 'generated_hash', 'generated_path',
    'mutable_dependency', 'image_population', 'object_bool', 'native_command', 'original_header', 'analyst',
    'capture_size', 'wrong_group', 'unsafe_argument', 'unfrozen_analysis'])
def test_v3_substitution_never_grants_clean_coverage(change):
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p, n = v3_fixture()
    stage = next(row for row in n['steps'] if row['id'] == 'baseline-compiler-evidence')
    value = json.loads(base64.b64decode(stage['output'])); row = value['records'][0]
    if change == 'context_digest': value['generated_context_sha256'] = 'f' * 64
    elif change == 'database_digest': value['analysis_database_sha256'] = 'f' * 64
    elif change == 'generated_hash': row['generated_dependencies']['include/config.h'] = 'f' * 64
    elif change == 'generated_path': row['generated_dependencies']['uncaptured.h'] = 'f' * 64
    elif change == 'mutable_dependency':
        deps = base64.b64decode(row['dependency_bytes']).replace(b'/work/analysis/generated-baseline', b'/work/build')
        row['dependency_bytes'], row['dependency_sha256'] = encoded(deps), hashlib.sha256(deps).hexdigest()
    elif change == 'image_population': row['toolchain_dependencies'] = []
    elif change == 'object_bool': row['object_bytes'] = True
    elif change == 'native_command': row['invocation'][1] = '-I/work/build/include'
    elif change == 'original_header': row['source_dependencies']['sum.hpp'] = 'f' * 64
    elif change == 'analyst': value['analyst_uid'] = 1000
    elif change in {'capture_size', 'wrong_group'}:
        capture = next(r for r in n['steps'] if r['id'] == 'baseline-generated-context')
        context = json.loads(base64.b64decode(capture['output']))
        if change == 'capture_size': context['captured_bytes'] += 1
        else: context['configuration'] = 'undefined'
        capture['output'] = encoded(json.dumps(context).encode())
    elif change == 'unsafe_argument':
        configure = next(r for r in n['steps'] if r['id'] == 'baseline-configure')
        db = json.loads(base64.b64decode(configure['artifacts']['compilation_database']))
        db[0]['arguments'] += ['-fplugin=/work/source/helper.so']
        configure['artifacts']['compilation_database'] = encoded(json.dumps(db).encode())
    else:
        analysis = next(r for r in n['steps'] if r['id'] == 'static-analysis')
        configure = next(r for r in n['steps'] if r['id'] == 'baseline-configure')
        analysis['artifacts']['compilation_database'] = configure['artifacts']['compilation_database']
    stage['output'] = encoded(json.dumps(value).encode())
    if change == 'unfrozen_analysis':
        assert validate_native(n, p)['complete'] is False
    else:
        with pytest.raises(ValueError): validate_native(n, p)


def test_v3_failed_native_compilation_is_not_silently_counted():
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p, n = v3_fixture()
    row = next(row for row in n['steps'] if row['id'] == 'baseline-compiler-evidence')
    value = json.loads(base64.b64decode(row['output']))
    value['records'][0]['compiler']['exit_code'] = 1
    row['output'] = encoded(json.dumps(value).encode())
    result = validate_native(n, p)
    assert result['build']['compiled_translation_units'] == ['sum.cpp']
    assert result['build']['implemented_command_scope_complete'] is False
    assert result['coverage']['header_context_verified'] is False


@pytest.mark.parametrize('phase', ['snapshot', 'compiler'])
def test_trusted_failure_envelopes_are_retained_without_granting_completion(phase):
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p, n = v3_fixture()
    key = 'baseline-generated-context' if phase == 'snapshot' else 'baseline-compiler-evidence'
    stage = next(row for row in n['steps'] if row['id'] == key)
    stage['exit_code'] = 1
    stage['output'] = encoded(json.dumps({'schema': 'nico.cpp-generated-failure.v1', 'configuration': 'baseline',
        'phase': phase, 'error': 'worker_generated_capture_unavailable'}).encode())
    if phase == 'snapshot':
        for row in n['steps']:
            if row['id'] in {'baseline-compiler-evidence', 'static-analysis'}:
                row.update(attempted=False, exit_code=None, duration_ms=0, output='', artifacts={})
    result = validate_native(n, p)
    assert result['build']['implemented_command_scope_complete'] is False
    assert next(row for row in result['build']['stages'] if row['id'] == key)['status'] == 'failed'
    assert result['build']['full_project_qualified'] is False


def test_nested_snapshot_content_is_checked_for_redaction_even_after_failure(monkeypatch):
    from nico import scanner_tool_runners
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p, n = v3_fixture()
    row = next(row for row in n['steps'] if row['id'] == 'baseline-generated-context')
    row['exit_code'] = 1
    row['output'] = encoded(json.dumps(snapshot(data=b'fixture-sensitive-marker')).encode())
    previous = scanner_tool_runners.redact_text
    monkeypatch.setattr(scanner_tool_runners, 'redact_text', lambda text: previous(text).replace('fixture-sensitive-marker', '[redacted]'))
    with pytest.raises(ValueError, match='redaction_required'): validate_native(n, p)


def test_changed_generated_input_is_rejected_on_second_read(tmp_path, monkeypatch):
    from nico import assessment_cpp_generated_context as m
    build = tmp_path / 'build'; (build / 'include').mkdir(parents=True)
    target = build / 'include/config.h'; target.write_bytes(b'original')
    private = tmp_path / 'private'; private.mkdir(mode=0o700)
    previous, count = m._stable_bytes, [0]
    def changing(*args):
        raw = previous(*args); count[0] += 1
        if count[0] == 1: target.write_bytes(b'mutated')
        return raw
    monkeypatch.setattr(m, '_stable_bytes', changing)
    with pytest.raises(ValueError, match='input_changed'): capture_headers(build, private / 'snapshot', HEADERS)
    assert list(private.iterdir()) == []


def test_full_consumer_dispatch_routes_snapshot_and_compiler_to_private_analyst(tmp_path):
    from nico.assessment_cpp_generated_context import SNAPSHOT_PROGRAM, COMPILER_PROGRAM
    from nico.assessment_cpp_full_project_execution import run_full_project
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import FakeDocker
    p, n = v3_fixture()
    for path in p['targets']: (tmp_path / path).write_bytes(path.encode())
    class GeneratedDocker(FakeDocker):
        def __call__(self, args, **kwargs):
            if SNAPSHOT_PROGRAM in args or COMPILER_PROGRAM in args:
                self.calls.append((args, kwargs))
                assert '--user=1001:1001' in args and '--interactive' in args
                request = json.loads(kwargs['input_bytes'])
                assert request['headers'] == HEADERS
                suffix = '-generated-context' if SNAPSHOT_PROGRAM in args else '-compiler-evidence'
                row = next(row for row in n['steps'] if row['id'] == request['configuration'] + suffix)
                return {'output': base64.b64decode(row['output']), 'exit_code': row['exit_code'],
                        'timed_out': False, 'output_truncated': False}
            return super().__call__(args, **kwargs)
    fake = GeneratedDocker(p, n)
    result = run_full_project(p, tmp_path, checkpoint=lambda: None, timeout_seconds=60, command=fake)
    assert result['native']['error'] is None
    assert validate_native(result['native'], p)['build']['implemented_command_scope_complete'] is True
    assert len([args for args, _ in fake.calls if SNAPSHOT_PROGRAM in args]) == 3
    assert len([args for args, _ in fake.calls if COMPILER_PROGRAM in args]) == 3
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']


def test_generated_programs_are_complete_standalone_python_not_import_stubs():
    from nico.assessment_cpp_generated_context import SNAPSHOT_PROGRAM, COMPILER_PROGRAM
    compile(SNAPSHOT_PROGRAM, '<generated-snapshot>', 'exec')
    compile(COMPILER_PROGRAM, '<generated-compiler>', 'exec')
    assert 'from nico' not in SNAPSHOT_PROGRAM
    assert 'from nico' not in COMPILER_PROGRAM


@pytest.mark.parametrize('language,phrase', [
    ('en', 'Generated headers: 1 captured; 1 included by direct compilation.'),
    ('es-MX', 'Encabezados generados: 1 capturados; 1 incluidos en la compilación directa.'),
])
def test_existing_report_exports_preserve_generated_header_origin(tmp_path, language, phrase):
    from nico.assessment_worker_receipts import validate_receipt
    from scripts.worker_protocol_fixture import identity
    from tests.test_assessment_cpp_full_project import wrap
    from nico.assessment_worker_jobs import _digest
    from scripts.qualify_cpp_full_project_integration import render_result
    p, n = v3_fixture(); receipt = wrap(n, p)
    _, record, _ = validate_receipt(identity(p), p, receipt['lease_id'], receipt['worker_id'], receipt)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(receipt))
    before = deepcopy(record)
    result = render_result({'canonical_record': record}, tmp_path, language)
    assert phrase in (tmp_path / ('owned-project-' + language + '.md')).read_text()
    assert result['production_report'] is False and result['automated_draft'] is True
    assert record == before


def test_owned_generated_fixture_uses_configure_file_and_keeps_default_control_unchanged():
    from scripts.qualify_cpp_full_project_control import FIXTURE
    from scripts.qualify_cpp_full_project_integration import fixture, plan
    assert fixture() == FIXTURE
    data = fixture(generated_headers=True)
    assert '#include "generated/config.h"' in data['sum.cpp']
    assert 'configure_file(config.h.in generated/config.h @ONLY)' in data['CMakeLists.txt']
    p = plan('sha256:' + 'a' * 64, generated_headers=True)
    assert p['configuration']['generated_headers'] == ['generated/config.h']
    assert 'generated/config.h' not in p['targets']
    assert p['targets']['config.h.in'] == hashlib.sha256(data['config.h.in'].encode()).hexdigest()
