"""Replay a retained GCC include spelling without granting external coverage."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from nico.assessment_cpp_clang_header_evidence import validate_clang_header_trace

FIXTURE = Path(__file__).parent / 'fixtures/cpp/clang-external-path-v17'


def retained():
    binding = json.loads((FIXTURE / 'bindings.json').read_bytes())
    raw = (FIXTURE / 'native-trace.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding['trace_sha256']
    kwargs = {key: binding[key] for key in ('source', 'context_id', 'standard', 'locations')}
    return raw, kwargs


def test_retained_gcc_external_paths_preserve_exact_owned_bindings():
    raw, kwargs = retained()
    native = json.loads(raw)
    assert any('..' in row['path'].split('/') for row in native['files'])
    proof = validate_clang_header_trace(raw, **kwargs)
    assert proof['normal_pass_completed'] is True
    assert proof['native_trace_sha256'] == hashlib.sha256(raw).hexdigest()
    assert {row['path'] for row in proof['bound_file_observations']} == set(kwargs['locations'])
    for row in proof['bound_file_observations']:
        assert row['source_sha256'] == kwargs['locations'][row['path']][2]
    for key in ('include_observed_files', 'parsed_ast_files', 'syntax_body_callback_files'):
        assert set(proof[key]) <= set(kwargs['locations'])
    assert proof['individual_checker_coverage_verified'] is False
    assert proof['line_branch_coverage_verified'] is False


@pytest.mark.parametrize('path', [
    '/tmp/../work/source/uncaptured.h',
    '/tmp/../work/analysis/generated-baseline/uncaptured.h',
    '/work/source/../outside.h',
    '/work/analysis/generated-baseline/../outside.h',
    '/work/sourceX/../source/uncaptured.h',
    '//work/source/uncaptured.h',
    '/tmp/../work/source',
    '/tmp/../work/analysis/generated-baseline',
    '/work/source',
    '/work/analysis/generated-baseline',
    '/work//source/uncaptured.h',
    '/work/./source/uncaptured.h',
    '/usr/..',
])
def test_external_spelling_cannot_hide_or_escape_an_owned_input(path):
    raw, kwargs = retained()
    native = json.loads(raw)
    native['files'] = [row for row in native['files'] if '..' not in row['path'].split('/')]
    assert validate_clang_header_trace(json.dumps(native).encode(), **kwargs)['normal_pass_completed'] is True
    row = deepcopy(next(row for row in native['files'] if row['path'] not in kwargs['locations']))
    row['path'] = path
    native['files'].append(row)
    with pytest.raises(ValueError, match='worker_clang_header_evidence_invalid'):
        validate_clang_header_trace(json.dumps(native).encode(), **kwargs)


@pytest.mark.parametrize('flag', ['diagnostic_errors', 'observation_overflow'])
def test_external_paths_never_upgrade_incomplete_native_state(flag):
    raw, kwargs = retained()
    native = json.loads(raw)
    native[flag] = True
    assert validate_clang_header_trace(json.dumps(native).encode(), **kwargs)['normal_pass_completed'] is False
