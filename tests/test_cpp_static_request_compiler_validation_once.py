"""Keep full compiler validation without parsing the same input twice."""
from copy import deepcopy

import pytest

from nico import assessment_cpp_compiler_collection as collection
from nico import assessment_cpp_project_static as static
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_completed_static_collection import fixture


@pytest.mark.parametrize('failing', [False, True])
def test_collection_static_request_does_not_duplicate_compiler_validation(tmp_path, monkeypatch, failing):
    expected, proof, _, _, inputs = fixture(tmp_path, failing=failing, include_inputs=True)
    calls = []
    original = collection.validate_project_compiler

    def checked(raw, request):
        calls.append((raw, _canonical(request)))
        return original(raw, request)

    monkeypatch.setattr(collection, 'validate_project_compiler', checked)
    monkeypatch.setattr(static, 'validate_project_compiler', checked)
    actual = static.project_static_request(*inputs, environment=expected['compiler_environment'],
        header_provenance=True, collect_completed_compiler_failures=True)
    assert actual == expected
    # Collection and independent environment binding each retain their full
    # validation. The unused direct parse must not add a third identical call.
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert actual['compiler_collection']['collection_complete'] is True
    assert actual['compiler_collection']['failed_contexts_count'] == len(proof['failed_contexts'])
    assert proof['compiler']['complete'] is (not failing)


@pytest.mark.parametrize('fault', ['raw-hash', 'missing-record', 'duplicate-context',
                                  'wrong-invocation', 'timeout', 'truncated'])
def test_collection_static_request_still_rejects_invalid_compiler_evidence(tmp_path, fault):
    expected, _, _, _, inputs = fixture(tmp_path, include_inputs=True)
    database, targets, snapshot, raw = inputs
    import json
    evidence = json.loads(raw)
    if fault == 'raw-hash':
        evidence['request_sha256'] = '0' * 64
    elif fault == 'missing-record':
        evidence['records'].pop()
    elif fault == 'duplicate-context':
        evidence['records'][1] = deepcopy(evidence['records'][0])
    elif fault == 'wrong-invocation':
        evidence['records'][0]['invocation'].append('-DOTHER=1')
    else:
        evidence['records'][0]['execution']['timed_out' if fault == 'timeout' else 'output_truncated'] = True
    with pytest.raises(ValueError):
        static.project_static_request(database, targets, snapshot, _canonical(evidence),
            environment=expected['compiler_environment'], header_provenance=True,
            collect_completed_compiler_failures=True)
