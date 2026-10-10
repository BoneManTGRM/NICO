"""Owned, inert environment receipts preserve compiler failure identities."""
from copy import deepcopy
import base64
import hashlib
import json

import pytest

from nico import assessment_cpp_static_environment as environment
from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection
from nico.assessment_cpp_project_compiler import _canonical, validate_project_compiler
from tests.test_cpp_compiler_collection import owned
from tests.test_cpp_static_environment import evidence as legacy_environment_evidence, observed

IMAGE = 'sha256:' + 'a' * 64


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def completed_fixture(tmp_path, *, failing=True):
    native, compiler_request, snapshot = owned(
        tmp_path, path='generated/owned_failure.cpp', failing=failing,
        directive=b'#error owned rejection' if failing else b'int generated(){return VALUE;}')
    compiler_raw = _canonical(native)
    collection = validate_project_compiler_collection(compiler_raw, compiler_request, snapshot)
    requested = environment.environment_request(
        compiler_request, compiler_raw, IMAGE,
        collect_completed_compiler_failures=True, snapshot=snapshot)
    raw_evidence = legacy_environment_evidence(requested)
    raw_evidence['schema'] = 'nico.cpp-static-environment.v2'
    for query in raw_evidence['queries'].values():
        body = base64.b64decode(query['predefines']['output']) + b'#define __cplusplus 202002L\n'
        query['predefines'] = observed(body)
    environment_raw = _canonical(raw_evidence)
    model = environment.validate_environment(environment_raw, requested)
    return compiler_request, compiler_raw, snapshot, collection, requested, raw_evidence, environment_raw, model


@pytest.mark.parametrize('failing', [True, False])
def test_completed_collection_binds_exact_request_native_and_environment_model(tmp_path, failing):
    compiler, raw, snapshot, collection, request, native, env_raw, model = completed_fixture(tmp_path, failing=failing)
    expected_collection_hash = digest(_canonical(collection))
    assert request['schema'] == 'nico.cpp-static-environment-request.v2'
    assert model['schema'] == 'nico.cpp-static-environment-model.v2'
    assert native['schema'] == 'nico.cpp-static-environment.v2'
    assert request['compiler_collection_sha256'] == model['compiler_collection_sha256'] == expected_collection_hash
    assert model['native_evidence_sha256'] == digest(env_raw)
    assert model['request_sha256'] == digest(_canonical(request))
    assert model['compiler_evidence_sha256'] == request['compiler_evidence_sha256'] == digest(raw)
    assert len(model['contexts']) == len(compiler['contexts']) == 4
    assert environment.bind_environment(model, compiler, raw,
        collect_completed_compiler_failures=True, snapshot=snapshot) == model
    assert collection['compiler'] == validate_project_compiler(raw, compiler)
    assert collection['compiler']['complete'] is (not failing)
    if failing:
        assert collection['failed_contexts'] == collection['unparsed_contexts'] == [
            c['context_id'] for c in compiler['contexts'][2:]]
        assert collection['compiler']['checked_contexts'] == [c['context_id'] for c in compiler['contexts'][:2]]
        for context in compiler['contexts'][2:]:
            assert model['contexts'][context['context_id']]['header_indices'] == []
            assert environment.context_dependencies(model, context['context_id']) == {}


def test_static_request_carries_failed_unparsed_collection_without_compiler_success(tmp_path):
    from nico.assessment_cpp_project_static import project_static_request
    compiler, raw, snapshot, collection, _, _, _, model = completed_fixture(tmp_path)
    database = _canonical([{k: c[k] for k in ('directory', 'file', 'arguments')}
                           for c in compiler['contexts']])
    request = project_static_request(database, compiler['targets'], snapshot, raw,
        environment=model, header_provenance=True, collect_completed_compiler_failures=True)
    assert request['schema'] == 'nico.cpp-project-static-request.v4'
    from nico.assessment_cpp_compiler_collection import collection_summary
    assert request['compiler_collection'] == collection_summary(collection)
    assert request['compiler_collection']['failed_contexts_count'] == 2
    assert request['compiler_collection']['unparsed_contexts_count'] == 2
    assert request['compiler_collection']['completed_contexts_count'] == 2
    assert collection['compiler']['complete'] is False
    assert request['compiler_collection']['failed_contexts_sha256'] == request['compiler_collection']['unparsed_contexts_sha256']
    assert len(request['contexts']) == 4
    for context in request['contexts'][2:]:
        assert context['source_dependencies'] == context['generated_dependencies'] == {}


@pytest.mark.parametrize('fault', ['missing-request', 'request-hash', 'wrong-image',
    'downgraded-native', 'forged-native-collection-field', 'missing-query',
    'wrong-query', 'query-digest', 'compiler-version', 'model', 'wrong-uid',
    'wrong-bool-exit', 'timeout', 'truncated', 'wrong-duration', 'duplicate-json'])
def test_environment_v2_rejects_incomplete_corrupt_or_downgraded_native_receipts(tmp_path, fault):
    *_, request, native, _, _ = completed_fixture(tmp_path)
    key = next(iter(native['queries']))
    if fault == 'missing-request': native.pop('request_sha256')
    elif fault == 'request-hash': native['request_sha256'] = '0' * 64
    elif fault == 'wrong-image': native['image_config_digest'] = 'sha256:' + 'b' * 64
    elif fault == 'downgraded-native': native['schema'] = 'nico.cpp-static-environment.v1'
    elif fault == 'forged-native-collection-field': native['compiler_collection_sha256'] = '0' * 64
    elif fault == 'missing-query': native['queries'].pop(key)
    elif fault == 'wrong-query': native['queries'][key]['invocation'].append('-DOTHER=1')
    elif fault == 'query-digest': native['queries'][key]['predefines']['output_sha256'] = '0' * 64
    elif fault == 'compiler-version': native['compiler_versions']['/usr/local/bin/g++'] = observed(b'13.1.0\n')
    elif fault == 'model': native['models']['std'] = '0' * 64
    elif fault == 'wrong-uid': native['analyst_uid'] = True
    elif fault == 'wrong-bool-exit': native['queries'][key]['predefines']['exit_code'] = False
    elif fault == 'timeout': native['queries'][key]['predefines']['timed_out'] = True
    elif fault == 'truncated': native['queries'][key]['predefines']['output_truncated'] = True
    elif fault == 'wrong-duration': native['duration_ms'] = environment.ENV_LIMITS['wall_seconds'] * 1000
    raw = _canonical(native)
    if fault == 'duplicate-json':
        raw = raw[:-1] + b',"request_sha256":"' + digest(_canonical(request)).encode() + b'"}'
    with pytest.raises(ValueError):
        environment.validate_environment(raw, request)


@pytest.mark.parametrize('fault', ['missing-collection', 'collection-hash', 'downgraded-model',
    'compiler-hash', 'request-hash', 'missing-context', 'wrong-context-query',
    'header-credit', 'header-population', 'model-hash', 'wrong-native-digest'])
def test_bound_environment_v2_rejects_forged_model_or_identity(tmp_path, fault):
    compiler, raw, snapshot, _, _, _, _, model = completed_fixture(tmp_path)
    context = compiler['contexts'][2]['context_id']
    if fault == 'missing-collection': model.pop('compiler_collection_sha256')
    elif fault == 'collection-hash': model['compiler_collection_sha256'] = '0' * 64
    elif fault == 'downgraded-model': model['schema'] = 'nico.cpp-static-environment-model.v1'
    elif fault == 'compiler-hash': model['compiler_evidence_sha256'] = '0' * 64
    elif fault == 'request-hash': model['request_sha256'] = '0' * 64
    elif fault == 'missing-context': model['contexts'].pop(context)
    elif fault == 'wrong-context-query': model['contexts'][context]['query'] = next(
        key for key in model['queries'] if key != model['contexts'][context]['query'])
    elif fault == 'header-credit': model['contexts'][context]['header_indices'] = [True]
    elif fault == 'header-population': model['header_population_sha256'] = '0' * 64
    elif fault == 'model-hash': model['models']['std'] = '0' * 64
    elif fault == 'wrong-native-digest': model['native_evidence_sha256'] = True
    with pytest.raises(ValueError):
        environment.bind_environment(model, compiler, raw,
            collect_completed_compiler_failures=True, snapshot=snapshot)


@pytest.mark.parametrize('bad_hash', [None, 'malformed', True])
@pytest.mark.parametrize('entry', ['analyzer', 'input-verifier', 'embedded-analyzer'])
def test_model_v2_requires_a_collection_hash_before_projection_or_native_input_reads(tmp_path, monkeypatch, bad_hash, entry):
    compiler, _, _, _, _, _, _, model = completed_fixture(tmp_path)
    if bad_hash is None:
        model.pop('compiler_collection_sha256')
    else:
        model['compiler_collection_sha256'] = bad_hash
    if entry == 'input-verifier':
        def unexpected_read(*args):
            pytest.fail('unbound model.v2 reached native input reads')
        monkeypatch.setattr(environment, '_regular_bytes', unexpected_read)
        with pytest.raises(ValueError, match='worker_project_static_environment_invalid'):
            environment.verify_environment_inputs(model)
    else:
        if entry == 'embedded-analyzer':
            namespace = dict(environment.__dict__)
            exec(compile(environment.STATIC_ENV_SUPPORT, '<owned-environment-support>', 'exec'), namespace)
            operation = namespace['analyzer_environment_arguments']
        else:
            operation = environment.analyzer_environment_arguments
        with pytest.raises(ValueError, match='worker_project_static_environment_invalid'):
            operation(compiler['contexts'][0], model)


@pytest.mark.parametrize('fault', ['missing-snapshot', 'snapshot-body', 'snapshot-hash',
    'snapshot-population', 'request-identity', 'compiler-native-digest'])
def test_environment_v2_rechecks_exact_compiler_request_and_snapshot(tmp_path, fault):
    compiler, raw, snapshot, *_ = completed_fixture(tmp_path)
    if fault == 'missing-snapshot': snapshot = None
    elif fault == 'snapshot-body': snapshot['files']['generated/owned_failure.cpp']['base64'] = base64.b64encode(b'#error changed\n').decode()
    elif fault == 'snapshot-hash': snapshot['files']['generated/owned_failure.cpp']['sha256'] = '0' * 64
    elif fault == 'snapshot-population': snapshot['file_population_sha256'] = '0' * 64
    elif fault == 'request-identity': compiler['context_membership_sha256'] = '0' * 64
    elif fault == 'compiler-native-digest': raw = raw.replace(b'"request_sha256":"', b'"request_sha256":"0', 1)
    with pytest.raises(ValueError):
        environment.environment_request(compiler, raw, IMAGE,
            collect_completed_compiler_failures=True, snapshot=snapshot)


@pytest.mark.parametrize('flag', [None, 0, 1, 'true'])
def test_environment_v2_policy_flag_cannot_be_coerced(tmp_path, flag):
    compiler, raw, snapshot, *_ = completed_fixture(tmp_path)
    with pytest.raises(ValueError, match='worker_static_environment_compiler_collection_invalid'):
        environment.environment_request(compiler, raw, IMAGE,
            collect_completed_compiler_failures=flag, snapshot=snapshot)


def test_completed_collection_is_opt_in_and_legacy_failed_compiler_still_rejects(tmp_path):
    compiler, raw, _, *_ = completed_fixture(tmp_path)
    with pytest.raises(ValueError, match='worker_static_environment_compiler_incomplete'):
        environment.environment_request(compiler, raw, IMAGE)


def test_legacy_v1_request_model_and_static_receipt_reconstruct_unchanged(tmp_path):
    from tests.test_cpp_static_environment import fixture
    from tests.test_cpp_project_static import native
    from nico.assessment_cpp_project_static import project_static_request, validate_project_static
    database, targets, snapshot, compiler, raw = fixture(tmp_path)
    expected = {'schema': 'nico.cpp-static-environment-request.v1',
                'contexts': [{'context_id': c['context_id'], 'source': c['analysis_file'],
                              'invocation': c['invocation'],
                              'toolchain_dependencies': json.loads(raw)['records'][i]['toolchain_dependencies']}
                             for i, c in enumerate(compiler['contexts'])],
                'compiler_evidence_sha256': digest(raw), 'image_config_digest': IMAGE,
                'models': dict(environment.MODEL_HASHES), 'limits': dict(environment.ENV_LIMITS)}
    request = environment.environment_request(compiler, raw, IMAGE)
    assert request == expected and 'compiler_collection_sha256' not in request
    model = environment.validate_environment(_canonical(legacy_environment_evidence(request)), request)
    assert model['schema'] == 'nico.cpp-static-environment-model.v1'
    assert 'compiler_collection_sha256' not in model
    assert environment.bind_environment(model, compiler, raw) == model
    static = project_static_request(database, targets, snapshot, raw)
    assert static['schema'] == 'nico.cpp-project-static-request.v1'
    assert validate_project_static(_canonical(native(static)), static)['complete'] is True
