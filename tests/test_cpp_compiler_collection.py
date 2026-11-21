"""Owned receipt fixtures test collection semantics, never native execution."""
from copy import deepcopy
import base64
import hashlib
import importlib.util
import json

import pytest

from nico.assessment_cpp_full_project import compilation_contexts
from nico.assessment_cpp_project_compiler import project_compiler_request, validate_project_compiler
from nico.assessment_cpp_project_snapshot import (
    capture_project_snapshot, project_snapshot_request, _project_file_population,
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def validate(raw, request, snapshot):
    # The original red proof exercises the old semantic result, not an import
    # failure. This fallback disappears once the additive capability exists.
    if importlib.util.find_spec('nico.assessment_cpp_compiler_collection') is None:
        original = validate_project_compiler(raw, request)
        return {'collection_complete': original['complete'], 'compiler': original}
    from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
    return validate_project_compiler_collection(raw, request, snapshot)


def owned(tmp_path, *, path='generated/owned_error.cc', failing=True, directive=b'#error owned rejection'):
    original = b'int value(){return VALUE;}\n'
    targets = {'unit.cpp': digest(original)}
    rows = []
    for index, file in enumerate(['/work/source/unit.cpp', '/work/source/unit.cpp',
                                  '/work/build/' + path, '/work/build/' + path]):
        rows.append({'directory': '/work/build', 'file': file,
                     'arguments': ['/usr/local/bin/g++', '-DVALUE=' + str(index),
                                   '-std=c++20', '-c', file, '-o', 'u' + str(index) + '.o']})
    database = canonical(rows)
    contexts = compilation_contexts(database, targets, '/work/build')
    build = tmp_path / 'build'
    source = build / path
    source.parent.mkdir(parents=True)
    source.write_bytes(b'// owned generated fixture\n' + directive + b'\n')
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    snapshot = capture_project_snapshot(build, private / 'generated-baseline',
                                         project_snapshot_request(contexts))
    request = project_compiler_request(database, targets, snapshot)
    records = []
    for context in request['contexts']:
        deps = ('nico_unit: ' + context['analysis_file'] + '\n').encode()
        generated = context['origin'] == 'generated'
        output = b''
        if generated and failing:
            line = directive.decode()
            keyword = line.index('error')
            column = len(line[:keyword].expandtabs(8)) + 1
            output = (context['analysis_file'] + ':2:' + str(column)
                      + ': error: #error ' + line[keyword + 5:].strip() + '\n').encode()
        records.append({
            'context_id': context['context_id'], 'invocation': context['invocation'],
            'execution': {'exit_code': 1 if output else 0, 'timed_out': False,
                          'output_truncated': False, 'duration_ms': 1,
                          'output': base64.b64encode(output).decode(),
                          'output_sha256': digest(output)},
            'dependency_bytes': '' if output else base64.b64encode(deps).decode(),
            'dependency_sha256': None if output else digest(deps),
            'source_dependencies': {} if output or generated else {'unit.cpp': targets['unit.cpp']},
            'generated_dependencies': {path: snapshot['files'][path]['sha256']} if generated and not output else {},
            'toolchain_dependencies': [], 'error': None,
        })
    evidence = {'schema': 'nico.cpp-project-compiler-evidence.v1',
                'request_sha256': digest(canonical(request)), 'analyst_uid': 1001,
                'records': records, 'duration_ms': 5}
    return evidence, request, snapshot


def output(record, raw):
    record['execution']['output'] = base64.b64encode(raw).decode()
    record['execution']['output_sha256'] = digest(raw)


@pytest.mark.parametrize('path', ['generated/owned_error.cc', 'other/deep/generated-unit.cpp'])
def test_generated_directive_is_collected_without_claiming_compiler_success(tmp_path, path):
    evidence, request, snapshot = owned(tmp_path, path=path)
    value = validate(canonical(evidence), request, snapshot)
    assert value['collection_complete'] is True, 'all attempted source-bound #error outcomes were not collected'
    assert value['compiler']['complete'] is False
    assert value['compiler']['checked_contexts'] == [c['context_id'] for c in request['contexts'][:2]]
    assert value['failed_contexts'] == value['unparsed_contexts'] == [c['context_id'] for c in request['contexts'][2:]]
    assert [r['path'] for r in value['failures']] == [path, path]
    assert all(r['line'] == 2 and r['column'] == 2 for r in value['failures'])
    assert value['native_evidence_sha256'] == digest(canonical(evidence))
    assert value['request_sha256'] == digest(canonical(request))
    assert value['snapshot_population_sha256'] == snapshot['file_population_sha256']
    assert value['snapshot_canonical_sha256'] == digest(canonical(snapshot))
    assert value['compiler']['static_analysis_executed'] is False
    assert value['compiler']['production_qualified'] is False
    assert value['compiler']['object_code_generated'] is False


def test_all_successful_owned_contexts_are_collected(tmp_path):
    evidence, request, snapshot = owned(tmp_path, failing=False, directive=b'int generated(){return VALUE;}')
    value = validate(canonical(evidence), request, snapshot)
    assert value['collection_complete'] is True and value['compiler']['complete'] is True
    assert value['failed_contexts'] == value['unparsed_contexts'] == value['failures'] == []


@pytest.mark.parametrize('directive', [b'  # error owned rejection', b'\t#error owned rejection', b'#error'])
def test_directive_spacing_and_actual_keyword_column_are_bound(tmp_path, directive):
    evidence, request, snapshot = owned(tmp_path, directive=directive)
    value = validate(canonical(evidence), request, snapshot)
    assert value['collection_complete'] is True
    assert value['failures'][0]['directive'] == directive.decode()


@pytest.mark.parametrize('fault', [
    'exit-two', 'signal', 'bool-exit', 'timeout', 'truncated', 'collector-error',
    'missing-execution', 'missing-record', 'duplicate-context', 'forged-invocation',
    'stale-request', 'bad-output-digest', 'foreign-path', 'wrong-line', 'wrong-column',
    'wrong-message', 'other-error', 'additional-error', 'unknown-diagnostic',
    'source-body', 'source-hash', 'snapshot-population', 'request-source-hash',
    'context-origin', 'claimed-pass', 'claimed-complete', 'failed-dependency-credit',
    'failed-generated-credit', 'failed-toolchain-credit', 'failed-dependency-bytes',
    'claimed-header-inclusion', 'malformed-output', 'stale-snapshot',
])
def test_non_supported_or_forged_outcomes_fail_closed(tmp_path, fault):
    evidence, request, snapshot = owned(tmp_path)
    record = evidence['records'][2]
    raw = base64.b64decode(record['execution']['output'])
    if fault == 'exit-two': record['execution']['exit_code'] = 2
    elif fault == 'signal': record['execution']['exit_code'] = -9
    elif fault == 'bool-exit': record['execution']['exit_code'] = True
    elif fault == 'timeout': record['execution']['timed_out'] = True
    elif fault == 'truncated': record['execution']['output_truncated'] = True
    elif fault == 'collector-error': record['error'] = 'worker_project_compiler_unavailable'
    elif fault == 'missing-execution': record['execution'] = None; record['error'] = 'worker_project_compiler_deadline'
    elif fault == 'missing-record': evidence['records'].pop()
    elif fault == 'duplicate-context': evidence['records'][3] = deepcopy(record)
    elif fault == 'forged-invocation': record['invocation'] = ['true']
    elif fault == 'stale-request': evidence['request_sha256'] = '0' * 64
    elif fault == 'bad-output-digest': record['execution']['output_sha256'] = '0' * 64
    elif fault == 'foreign-path': output(record, raw.replace(b'/work/analysis/', b'/work/source/'))
    elif fault == 'wrong-line': output(record, raw.replace(b':2:2:', b':1:2:'))
    elif fault == 'wrong-column': output(record, raw.replace(b':2:2:', b':2:1:'))
    elif fault == 'wrong-message': output(record, raw.replace(b'owned rejection', b'forged rejection'))
    elif fault == 'other-error': output(record, raw.replace(b'#error owned rejection', b'unknown type name'))
    elif fault == 'additional-error': output(record, raw + b'cc1plus: fatal error: permission denied\n')
    elif fault == 'unknown-diagnostic': output(record, raw + b'collector failed to start\n')
    elif fault == 'source-body':
        snapshot['files'][request['contexts'][2]['path']]['base64'] = base64.b64encode(b'// substituted').decode()
    elif fault == 'source-hash': snapshot['files'][request['contexts'][2]['path']]['sha256'] = '0' * 64
    elif fault == 'snapshot-population': snapshot['file_population_sha256'] = '0' * 64
    elif fault == 'request-source-hash': request['generated_files'][request['contexts'][2]['path']]['sha256'] = '0' * 64; evidence['request_sha256'] = digest(canonical(request))
    elif fault == 'context-origin': request['contexts'][2]['origin'] = 'original'; evidence['request_sha256'] = digest(canonical(request))
    elif fault == 'claimed-pass':
        context = request['contexts'][2]; deps = ('nico_unit: ' + context['analysis_file'] + '\n').encode()
        record['execution']['exit_code'] = 0
        record.update(dependency_bytes=base64.b64encode(deps).decode(), dependency_sha256=digest(deps),
                      generated_dependencies={context['path']: request['generated_files'][context['path']]['sha256']})
    elif fault == 'claimed-complete': evidence['collection_complete'] = True
    elif fault == 'failed-dependency-credit': record['source_dependencies'] = dict(request['targets'])
    elif fault == 'failed-generated-credit': record['generated_dependencies'] = {request['contexts'][2]['path']: request['generated_files'][request['contexts'][2]['path']]['sha256']}
    elif fault == 'failed-toolchain-credit': record['toolchain_dependencies'] = ['/usr/include/stdint.h']
    elif fault == 'failed-dependency-bytes':
        record['dependency_bytes'] = base64.b64encode(b'nico_unit: /usr/include/stdint.h\n').decode()
        record['dependency_sha256'] = digest(b'nico_unit: /usr/include/stdint.h\n')
    elif fault == 'claimed-header-inclusion': record['header_context_verified'] = True
    elif fault == 'malformed-output': record['execution']['output'] = 'invalid***'
    elif fault == 'stale-snapshot': snapshot['database_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        validate(canonical(evidence), request, snapshot)


def test_original_source_error_is_not_a_supported_generated_failure(tmp_path):
    evidence, request, snapshot = owned(tmp_path)
    record = evidence['records'][0]
    record['execution']['exit_code'] = 1
    output(record, b'/work/source/unit.cpp:1:2: error: #error owned rejection\n')
    record.update(dependency_bytes='', dependency_sha256=None, source_dependencies={})
    with pytest.raises(ValueError):
        validate(canonical(evidence), request, snapshot)


def test_changed_immutable_body_cannot_retain_old_diagnostic(tmp_path):
    evidence, request, snapshot = owned(tmp_path)
    path = request['contexts'][2]['path']
    raw = b'// owned generated fixture\n#error different source body\n'
    snapshot['files'][path] = {'base64': base64.b64encode(raw).decode(),
                              'sha256': digest(raw), 'bytes': len(raw)}
    snapshot['captured_bytes'] = len(raw)
    snapshot['file_population_sha256'] = _project_file_population(snapshot['files'])
    request['generated_files'][path] = {'sha256': digest(raw), 'bytes': len(raw)}
    request['snapshot_population_sha256'] = snapshot['file_population_sha256']
    evidence['request_sha256'] = digest(canonical(request))
    with pytest.raises(ValueError):
        validate(canonical(evidence), request, snapshot)


def test_boolean_context_index_is_not_an_integer_plan_identity(tmp_path):
    evidence, request, snapshot = owned(tmp_path)
    request['contexts'][0]['index'] = False
    evidence['request_sha256'] = digest(canonical(request))
    with pytest.raises(ValueError):
        validate(canonical(evidence), request, snapshot)


def test_boolean_generated_byte_count_is_not_an_integer_snapshot_binding(tmp_path):
    evidence, request, snapshot = owned(tmp_path, failing=False, directive=b';')
    path = request['contexts'][2]['path']
    raw = b';'
    snapshot['files'][path] = {'base64': base64.b64encode(raw).decode(),
                              'sha256': digest(raw), 'bytes': 1}
    snapshot['captured_bytes'] = 1
    snapshot['file_population_sha256'] = _project_file_population(snapshot['files'])
    request['generated_files'][path] = {'sha256': digest(raw), 'bytes': True}
    request['snapshot_population_sha256'] = snapshot['file_population_sha256']
    for record in evidence['records'][2:]:
        record['generated_dependencies'][path] = digest(raw)
    evidence['request_sha256'] = digest(canonical(request))
    with pytest.raises(ValueError):
        validate(canonical(evidence), request, snapshot)
