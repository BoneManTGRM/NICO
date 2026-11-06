"""Console diagnostics disclose classifications without changing acceptance."""
import json

import pytest

from nico.assessment_cpp_runtime_scope import retained_runtime_bytes, validate_retained_runtime
from scripts.qualify_cpp_project_configuration import (
    runtime_failure_diagnostic, validate_qualification_runtime,
)
from tests.test_cpp_runtime_collection import fixture


def test_missing_runtime_rejection_keeps_original_error_and_small_summary(tmp_path, capsys):
    retained, targets, options, scope = fixture(tmp_path, kind=None)
    raw = retained_runtime_bytes(retained['interfaces'], retained['plan'], None)
    probe = {'status': 'UNPROVEN', 'error': 'worker_configuration_probe_native_tests_failed',
             'runtime_evidence': None}
    with pytest.raises(ValueError, match='^worker_runtime_evidence_invalid$'):
        validate_qualification_runtime(raw, targets, options, scope, probe, retained['plan'])
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary['probe_error'] == probe['error']
    assert summary['probe_status'] == 'UNPROVEN'
    assert summary['runtime_present'] is False
    assert summary['runtime_is_object'] is False
    assert len(output.encode()) < 1024
    assert probe['status'] == 'UNPROVEN'


def test_valid_runtime_result_is_unchanged_and_silent(tmp_path, capsys):
    retained, targets, options, scope = fixture(tmp_path, kind=None)
    raw = retained_runtime_bytes(retained['interfaces'], retained['plan'], retained['evidence'])
    expected = validate_retained_runtime(raw, targets, options, scope)
    assert validate_qualification_runtime(raw, targets, options, scope,
        {'runtime_evidence': retained['evidence']}, retained['plan']) == expected
    assert capsys.readouterr().out == ''


def test_arbitrary_fields_and_secrets_never_enter_summary():
    private = 'PRIVATE_TOKEN_and_customer_source_' * 10000
    probe = {'status': private, 'error': private, 'output': private,
        'runtime_evidence': {'schema': private, 'error': private, private: private,
            'plan_sha256': private, 'duration_ms': private, 'complete': private}}
    summary = runtime_failure_diagnostic(probe, {'total_seconds': 6000, 'private': private})
    output = json.dumps(summary)
    assert 'PRIVATE' not in output and len(output) < 1024
    assert summary['probe_status'] == summary['probe_error'] == 'other'
    assert not summary['runtime_schema_known']
    assert not summary['runtime_fields_match']
    assert not summary['plan_digest_matches']
    assert not summary['runtime_error_format_valid']


@pytest.mark.parametrize('value', [None, [], 'private', {'schema': [], 'error': {}, 'duration_ms': True}])
def test_malformed_runtime_is_classified_without_copying_values(value):
    summary = runtime_failure_diagnostic({'runtime_evidence': value}, {'total_seconds': 6000})
    assert summary['runtime_is_object'] is isinstance(value, dict)
    assert not summary['runtime_schema_known']
    assert not summary['duration_is_integer']


def test_failed_log_write_cannot_replace_original_rejection(monkeypatch):
    import nico.assessment_cpp_runtime_scope as scope
    original = ValueError('worker_runtime_evidence_invalid')
    def reject(*args):
        raise original
    def broken_output(*args, **kwargs):
        raise OSError('output unavailable')
    monkeypatch.setattr(scope, 'validate_retained_runtime', reject)
    monkeypatch.setattr('builtins.print', broken_output)
    with pytest.raises(ValueError) as caught:
        validate_qualification_runtime(b'{}', {}, {}, {}, {}, {})
    assert caught.value is original
